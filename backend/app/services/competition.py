"""Database Rescue workflow. Authoritative records are committed synchronously.

SQL execution happens outside metadata transactions. Unique awards, immutable
reports and database leases make retries safe across serving workers.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import io
import json
import logging
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.user import User, UserRole
from app.models.competition import (
    Competition, CompetitionDraft, CompetitionEvent, CompetitionExecutionLease,
    CompetitionIncidentVersion, CompetitionParticipation, CompetitionReward,
    CompetitionRun, CompetitionSubmission, CompetitionReview,
    CompetitionSurvey,
)
from app.core.competition_executor import digest, execute, public_database
from app.core.competition_comparator import matches

logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


def utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def fail(message, status=400):
    raise HTTPException(status_code=status, detail=message)


def require_enabled():
    if not settings.COMPETITIONS_ENABLED:
        fail("Competition is not enabled yet.", 404)


def within_window(competition):
    instant = now()
    return (not competition.opens_at or utc(competition.opens_at) <= instant) and (not competition.closes_at or instant < utc(competition.closes_at))


def get_competition(db, competition_id, user, *, mutate=False):
    comp = db.get(Competition, competition_id)
    if not comp or not comp.published:
        fail("Competition not found.", 404)
    groups = comp.config.get("class_groups", [])
    if user.role == UserRole.STUDENT and groups and (user.class_group or "").strip() not in groups:
        fail("This competition is not assigned to your class.", 403)
    if mutate and not within_window(comp):
        fail("This competition is outside its participation window.", 403)
    return comp


def event(db, participation_id, kind, *, item_key=None, payload=None):
    db.add(CompetitionEvent(participation_id=participation_id, item_key=item_key, event_type=kind, payload=payload or {}))


def join(db, competition_id, user):
    comp = get_competition(db, competition_id, user, mutate=True)
    if user.role != UserRole.STUDENT:
        fail("Use the instructor incident preview to rehearse; staff do not enter participant rankings.", 403)
    part = db.query(CompetitionParticipation).filter_by(competition_id=comp.id, user_id=user.id).first()
    if part:
        return part
    part = CompetitionParticipation(competition_id=comp.id, user_id=user.id, cohort=(user.class_group or "").strip(), phase="gameplay", created_at=now())
    db.add(part)
    try:
        db.flush()
        event(db, part.id, "joined", payload={"competition_hash": comp.content_hash})
        db.commit()
    except IntegrityError:
        db.rollback()
        part = db.query(CompetitionParticipation).filter_by(competition_id=competition_id, user_id=user.id).one()
    return part


def participation(db, participation_id, user, *, mutate=False):
    part = db.get(CompetitionParticipation, participation_id)
    if not part or part.user_id != user.id:
        fail("Participation not found.", 404)
    comp = get_competition(db, part.competition_id, user, mutate=mutate)
    return part, comp


def item_versions(part, comp):
    return {f"gameplay:{i}": v for i, v in enumerate(comp.config["missions"])}


def competition_config(comp):
    """Expose current settings while preserving frozen legacy JSON in storage."""
    config = comp.config
    return {"missions": config["missions"], "class_groups": config.get("class_groups", []),
            "leaderboard": config.get("leaderboard", True), "time_tiebreak": config.get("time_tiebreak", True),
            "points": config.get("points", config.get("restoration_xp", {"easy": 10, "medium": 20, "hard": 30}))}


def item(db, participation_id, key, user, *, mutate=False):
    part, comp = participation(db, participation_id, user, mutate=mutate)
    ids = item_versions(part, comp)
    if key not in ids:
        fail("Incident not found in this competition.", 404)
    version = db.get(CompetitionIncidentVersion, ids[key])
    if not version:
        fail("The published incident is unavailable.", 503)
    return part, comp, version


def get_draft(db, participation_id, key):
    draft = db.query(CompetitionDraft).filter_by(participation_id=participation_id, item_key=key).first()
    if not draft:
        draft = CompetitionDraft(participation_id=participation_id, item_key=key, payload={}, revision=0)
        db.add(draft)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        draft = db.query(CompetitionDraft).filter_by(participation_id=participation_id, item_key=key).one()
    return draft


def save_draft(db, part_id, key, user, request):
    _part, _comp, version = item(db, part_id, key, user, mutate=True)
    version_id = version.id
    report = request.report.model_dump()
    if report["component_id"] and report["component_id"] not in {c["id"] for c in version.document["components"]}:
        fail("Choose a component from this incident.")
    previous = get_draft(db, part_id, key)
    changes = {k: v for k, v in report.items() if previous.payload.get(k) != v}
    result = db.execute(update(CompetitionDraft).where(CompetitionDraft.participation_id == part_id,
                        CompetitionDraft.item_key == key, CompetitionDraft.revision == request.revision)
                        .values(payload=report, revision=request.revision + 1, updated_at=now()))
    if result.rowcount != 1:
        db.rollback()
        fail("This draft changed in another tab. Reload the saved draft before saving again.", 409)
    event(db, part_id, "draft_saved", item_key=key, payload={"revision": request.revision + 1, "incident_version_id": version_id, "changes": changes})
    db.commit()
    return {"revision": request.revision + 1, "report": report}


def acquire(db, user_id):
    lease = db.get(CompetitionExecutionLease, user_id)
    if not lease:
        db.add(CompetitionExecutionLease(user_id=user_id, token="", expires_at=now() - timedelta(seconds=1)))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    token = uuid.uuid4().hex
    result = db.execute(update(CompetitionExecutionLease).execution_options(synchronize_session=False).where(CompetitionExecutionLease.user_id == user_id,
                        CompetitionExecutionLease.expires_at <= now()).values(token=token, expires_at=now() + timedelta(seconds=40)))
    if result.rowcount != 1:
        db.rollback()
        fail("Another competition action is running. Wait for it to finish and retry.", 409)
    db.commit()
    return token


def release(db, user_id, token):
    db.execute(update(CompetitionExecutionLease).execution_options(synchronize_session=False).where(CompetitionExecutionLease.user_id == user_id,
                CompetitionExecutionLease.token == token).values(expires_at=now() - timedelta(seconds=1)))
    db.commit()


def finish_phase(db, part_id, phase, user):
    part, comp = participation(db, part_id, user, mutate=True)
    if phase != "gameplay":
        fail("Unknown competition stage.", 404)
    keys = list(item_versions(part, comp))
    submitted = {d.item_key for d in db.query(CompetitionDraft).filter_by(participation_id=part_id, submitted=1)}
    if not set(keys).issubset(submitted):
        fail("Attempt and submit every required incident report first. Correct answers are not required.")
    part.phase = "complete"
    part.phase_active = 0
    event(db, part.id, "phase_submitted", payload={"phase": phase})
    db.commit()


def help_checkpoint(db, part_id, key, user):
    part, _comp, version = item(db, part_id, key, user, mutate=True)
    hints = version.document["checkpoints"]
    draft = get_draft(db, part.id, key)
    # Atomic bounded increment also handles two concurrent reveal clicks.
    db.execute(update(CompetitionDraft).where(CompetitionDraft.id == draft.id, CompetitionDraft.help_level < len(hints))
               .values(help_level=CompetitionDraft.help_level + 1))
    db.refresh(draft)
    level = draft.help_level
    event(db, part_id, "help_revealed", item_key=key, payload={"level": level, "incident_version_id": version.id})
    db.commit()
    return {"level": level, "checkpoints": hints[:level]}


def judge(document, component_id, query):
    deadline = time.monotonic() + settings.COMPETITION_JUDGE_SECONDS
    outcomes = []
    for scenario in document["scenarios"]:
        for component in document["components"]:
            sql = query if component["id"] == component_id else component["query"]
            result = execute(document["schema_sql"], scenario["seed_sql"], sql, deadline=deadline)
            passed = matches(result, scenario["approved_outputs"][component["id"]], order_sensitive=component.get("order_sensitive", False), numeric_tolerance=component.get("numeric_tolerance", 0))
            outcomes.append({"scenario": scenario["id"], "component": component["id"], "passed": passed, "executed": result["success"]})
    return {"restored": all(x["passed"] for x in outcomes), "diagnosis_location_correct": component_id == document["culprit_component"],
            "passed_checks": sum(x["passed"] for x in outcomes), "total_checks": len(outcomes), "outcomes": outcomes}


def run_sql(db, part_id, key, user, request, *, check=False):
    part, _comp, version = item(db, part_id, key, user, mutate=True)
    document, version_id, user_id = version.document, version.id, user.id
    if request.component_id and request.component_id not in {c["id"] for c in document["components"]}:
        fail("Unknown query component.")
    if check and not request.component_id:
        fail("Select the component you want to repair.")
    token = acquire(db, user_id)
    try:
        db.commit()
        if check:
            result = judge(document, request.component_id, request.query)
            public_result = {k: result[k] for k in ("restored", "passed_checks", "total_checks")}
        else:
            scenario = next(s for s in document["scenarios"] if s["visible"])
            result = execute(document["schema_sql"], scenario["seed_sql"], request.query, preview=True)
            public_result = result
        # Recheck stage/window after SQL; a staff closure cannot be bypassed by
        # starting a request before the close. The run is still saved as evidence.
        run = CompetitionRun(participation_id=part_id, item_key=key, kind="check" if check else "investigation", component_id=request.component_id, sql=request.query, result=result)
        db.add(run)
        db.flush()
        event(db, part_id, "repair_checked" if check else "query_run", item_key=key, payload={"run_id": run.id, "incident_version_id": version_id})
        db.commit()
        return {"run_id": run.id, **public_result}
    finally:
        release(db, user_id, token)


def _award(db, part_id, key, kind, xp, submission_id):
    if not db.query(CompetitionReward.id).filter_by(participation_id=part_id, item_key=key, kind=kind).first():
        db.add(CompetitionReward(participation_id=part_id, item_key=key, kind=kind, xp=xp, submission_id=submission_id))


def submit_report(db, part_id, key, user, request):
    # Ownership is checked before idempotency lookups, including after closing.
    part, comp = participation(db, part_id, user)
    if key not in item_versions(part, comp):
        fail("Incident not found in this competition.", 404)
    existing = db.query(CompetitionSubmission).filter_by(participation_id=part_id, request_key=request.request_key).first()
    if existing and (existing.item_key != key or existing.draft_revision != request.revision):
        fail("This submission key belongs to a different report.", 409)
    if existing and existing.status == "graded":
        return submission_response(existing, comp)
    if existing:
        # Recovery rejudges only the immutable accepted artifact, even after closing.
        version = db.get(CompetitionIncidentVersion, existing.incident_version_id)
        if not version:
            fail("The stored incident version is unavailable.", 503)
    else:
        _part, _comp, version = item(db, part_id, key, user, mutate=True)
    document, version_id, config, user_id = version.document, version.id, competition_config(comp), user.id
    draft = get_draft(db, part_id, key)
    payload = dict(existing.payload if existing else draft.payload)
    if not existing and draft.revision != request.revision:
        fail("Save this draft before submitting it.", 409)
    simple_report = document.get("report_style") == "verdict"
    fields = ("component_id", "explanation") if simple_report else ("component_id", "evidence", "diagnosis", "repair_sql", "explanation")
    if any(not str(payload.get(f, "")).strip() for f in fields):
        fail("Submit a component and short explanation." if simple_report else "Submit evidence, a suspected component and cause, a repair attempt, and a consequence explanation.")
    if simple_report and not payload.get("verdict"):
        fail("Choose whether the SQL is correct or incorrect.")
    if simple_report and payload.get("verdict") == "incorrect" and not payload.get("repair_sql", "").strip():
        fail("Provide a SQL repair attempt for an incorrect verdict.")
    if payload["component_id"] not in {c["id"] for c in document["components"]}:
        fail("Choose a component from this incident.")
    if simple_report and payload.get("verdict") == "correct":
        # Freeze the SQL actually judged, matching the original query shown in the UI.
        payload["repair_sql"] = next(c["query"] for c in document["components"] if c["id"] == payload["component_id"])
    run = db.get(CompetitionRun, payload.get("run_id")) if payload.get("run_id") else None
    if not simple_report and (not run or run.participation_id != part_id or run.item_key != key or run.kind != "investigation"):
        fail("Run an investigation query before submitting this report.")
    token = acquire(db, user_id)
    submission_id = None
    try:
        # Refresh the idempotency lookup after obtaining the cross-worker lease.
        existing = db.query(CompetitionSubmission).filter_by(participation_id=part_id, request_key=request.request_key).first()
        if existing and existing.status == "graded":
            return submission_response(existing, comp)
        if not existing:
            existing = CompetitionSubmission(participation_id=part_id, item_key=key, request_key=request.request_key,
                incident_version_id=version_id, draft_revision=request.revision, payload=payload, help_level=draft.help_level, created_at=now())
            db.add(existing)
            db.flush()
        draft = db.query(CompetitionDraft).filter_by(participation_id=part_id, item_key=key).one()
        draft.submitted = 1  # Presence/attempt requirements already passed; grading is independent.
        submission_id = existing.id
        submitted_keys = {d.item_key for d in db.query(CompetitionDraft).filter_by(participation_id=part_id, submitted=1)}
        if set(item_versions(part, comp)).issubset(submitted_keys):
            part.phase, part.phase_active = "complete", 0
        event(db, part_id, "report_accepted", item_key=key, payload={"submission_id": submission_id, "incident_version_id": version_id})
        db.commit()  # Immutable report survives worker failure; release pool slot.
        component = next(c for c in document["components"] if c["id"] == payload["component_id"])
        query = component["query"] if simple_report and payload.get("verdict") == "correct" else payload["repair_sql"]
        result = judge(document, payload["component_id"], query)
        if simple_report:
            # All currently authored incidents contain one private semantic fault.
            result["verdict_correct"] = payload["verdict"] == "incorrect"
            result["restored"] = result["restored"] and result["verdict_correct"]
        existing = db.get(CompetitionSubmission, submission_id)
        existing.result, existing.status, existing.graded_at = result, "graded", now()
        draft = db.query(CompetitionDraft).filter_by(participation_id=part_id, item_key=key).one()
        draft.submitted = 1
        draft.restored = int(bool(draft.restored) or result["restored"])
        if result["restored"]:
            _award(db, part_id, key, "restoration", config["points"][document["difficulty"]], submission_id)
        event(db, part_id, "report_submitted", item_key=key, payload={"submission_id": submission_id, "incident_version_id": version_id, "restored": result["restored"]})
        db.commit()
        return submission_response(existing, comp)
    except Exception:
        logger.exception("Competition judgement failed for submission %s", submission_id)
        db.rollback()
        if submission_id:
            saved = db.get(CompetitionSubmission, submission_id)
            if saved and saved.status != "graded":
                saved.status = "judge_error"
                db.commit()
                return submission_response(saved, comp)
        raise
    finally:
        release(db, user_id, token)


def submission_response(submission, competition):
    show = submission.status == "graded"
    result = submission.result or {}
    return {"id": submission.id, "status": submission.status, "submitted": submission.status in {"graded", "judge_error", "pending"},
            "feedback": {k: result[k] for k in ("restored", "passed_checks", "total_checks", "verdict_correct") if k in result} if show else None}


def public_incident(db, part_id, key, user):
    part, comp, version = item(db, part_id, key, user)
    document = version.document
    scenario = next(s for s in document["scenarios"] if s["visible"])
    draft = get_draft(db, part_id, key)
    event(db, part_id, "incident_opened", item_key=key, payload={"incident_version_id": version.id})
    draft_data = {"revision": draft.revision, "report": draft.payload, "submitted": bool(draft.submitted)}
    help_level = draft.help_level
    db.commit()
    public = {k: document[k] for k in ("title", "topic", "difficulty", "complaint", "business_rules", "schema_sql")}
    public["report_style"] = document.get("report_style", "investigation")
    public["points"] = competition_config(comp)["points"][document["difficulty"]]
    public["components"] = [{k: c[k] for k in ("id", "label", "purpose", "query")} for c in document["components"]]
    public["features"] = [{"component_id": c["id"], "label": c["label"], "output": execute(document["schema_sql"], scenario["seed_sql"], c["query"], preview=True)} for c in document["components"]]
    public["database"] = public_database(document["schema_sql"], scenario["seed_sql"])
    public["draft"] = draft_data
    public["assistance_allowed"] = True
    public["checkpoints"] = document["checkpoints"][:help_level] if public["assistance_allowed"] else []
    public["checkpoint_count"] = len(document["checkpoints"]) if public["assistance_allowed"] else 0
    public["runs"] = [{"id": r.id, "sql": r.sql, "result": r.result} for r in db.query(CompetitionRun).filter_by(participation_id=part_id, item_key=key, kind="investigation").order_by(CompetitionRun.id.desc()).limit(15)]
    public["read_only"] = not within_window(comp)
    return public


def summary(db, part, comp):
    drafts = {d.item_key: d for d in db.query(CompetitionDraft).filter_by(participation_id=part.id)}
    items = []
    for key, version_id in item_versions(part, comp).items():
        version = db.get(CompetitionIncidentVersion, version_id)
        draft = drafts.get(key)
        entry = {"key": key, "title": version.document["title"], "difficulty": version.document["difficulty"],
                 "submitted": bool(draft and draft.submitted)}
        entry["restored"] = bool(draft and draft.restored)
        entry["points"] = competition_config(comp)["points"][version.document["difficulty"]]
        items.append(entry)
    restorations = db.query(CompetitionReward).filter_by(participation_id=part.id, kind="restoration").all()
    difficult = any(i["difficulty"] in {"medium", "hard"} and i["key"] in {r.item_key for r in restorations} for i in items)
    badges = [f"{comp.topic.title()} Rescuer"] if len(restorations) >= 2 and difficult else []
    complete = all(i["submitted"] for i in items)
    return {"id": part.id, "competition_id": comp.id, "phase": "complete" if complete else "gameplay",
            "participation_complete": complete,
            "points": sum(r.xp for r in restorations), "badges": badges, "items": items}


def metadata(comp):
    return {"id": comp.id, "title": comp.title, "description": comp.description, "topic": comp.topic,
            "opens_at": utc(comp.opens_at), "closes_at": utc(comp.closes_at), "open": within_window(comp),
            "mission_count": len(comp.config["missions"]), "time_tiebreak": competition_config(comp)["time_tiebreak"]}


def leaderboard(db, comp, user):
    if not comp.config.get("leaderboard", True):
        return {"rows": [], "updated_at": now(), "enabled": False}
    rows = []
    parts = db.query(CompetitionParticipation).filter_by(competition_id=comp.id).all()
    for part in parts:
        if part.cohort in settings.ANALYTICS_EXCLUDED_CLASS_GROUPS:
            continue
        # Students see their own cohort, including the empty/unassigned cohort.
        if user.role == UserRole.STUDENT and part.cohort != (user.class_group or "").strip():
            continue
        rewards = db.query(CompetitionReward).filter_by(participation_id=part.id, kind="restoration").all()
        points = sum(r.xp for r in rewards)
        # Use the first accepted successful report, not worker grading/retry time.
        accepted = [utc(db.get(CompetitionSubmission, r.submission_id).created_at) for r in rewards]
        elapsed = max(0, (max(accepted) - utc(part.created_at)).total_seconds()) if accepted else None
        alias = "Engineer " + digest({"participant": part.id, "competition": comp.content_hash})[:8].upper()
        rows.append({"alias": alias, "points": points, "elapsed_seconds": elapsed, "is_you": part.user_id == user.id})
    use_time = competition_config(comp)["time_tiebreak"]
    def score(row):
        return (-row["points"], row["elapsed_seconds"] if use_time and row["elapsed_seconds"] is not None else 0)
    rows.sort(key=lambda r: (*score(r), r["alias"]))
    rank, previous = 0, None
    for index, row in enumerate(rows):
        if score(row) != previous:
            rank = index + 1
        row["rank"] = rank
        previous = score(row)
    return {"rows": rows, "updated_at": now(), "enabled": True}


def export_rows(db, comp, mode):
    if not settings.RESEARCH_EXPORT_SALT:
        fail("RESEARCH_EXPORT_SALT is not configured.", 503)
    population = db.query(CompetitionParticipation).filter_by(competition_id=comp.id).all()
    parts = {p.id: p for p in population if p.cohort not in settings.ANALYTICS_EXCLUDED_CLASS_GROUPS}

    def identity(part):
        anon = hmac.new(settings.RESEARCH_EXPORT_SALT.encode(), str(part.user_id).encode(), hashlib.sha256).hexdigest()
        return {"participant": anon, "competition_id": comp.id, "competition_hash": comp.content_hash, "cohort": part.cohort}

    rows = []
    for part in parts.values():
        if mode == "participation":
            data = summary(db, part, comp)
            rows.append({**identity(part), "participation_complete": data["participation_complete"], "points": data["points"],
                         "missing_activities": ";".join(i["key"] for i in data["items"] if not i["submitted"])})
        elif mode in {"submissions", "outcomes"}:
            submissions = db.query(CompetitionSubmission).filter_by(participation_id=part.id).order_by(CompetitionSubmission.id).all()
            if mode == "outcomes":
                latest = {s.item_key: s for s in submissions}
                for key, version_id in item_versions(part, comp).items():
                    submission = latest.get(key)
                    review = db.query(CompetitionReview).filter_by(submission_id=submission.id).order_by(CompetitionReview.id.desc()).first() if submission else None
                    rows.append({**identity(part), "item": key, "incident_version": version_id,
                                 "submission_status": submission.status if submission else "missing", "repair_correct": (submission.result or {}).get("restored") if submission else None,
                                 "diagnosis_score": review.diagnosis_score if review else None, "explanation_score": review.explanation_score if review else None,
                                 "rubric_version": review.rubric_version if review else "rescue-v1", "help_level": submission.help_level if submission else None})
            else:
                for s in submissions:
                    if s.item_key not in item_versions(part, comp):
                        continue
                    review = db.query(CompetitionReview).filter_by(submission_id=s.id).order_by(CompetitionReview.id.desc()).first()
                    rows.append({**identity(part), "submission_id": s.id, "item": s.item_key, "incident_version": s.incident_version_id,
                                 "status": s.status, "created_at": s.created_at, "help_level": s.help_level,
                                 "payload": json.dumps(s.payload), "outcome": json.dumps(s.result),
                                 "diagnosis_score": review.diagnosis_score if review else None, "explanation_score": review.explanation_score if review else None})
        elif mode == "events":
            for e in db.query(CompetitionEvent).filter_by(participation_id=part.id).order_by(CompetitionEvent.id):
                rows.append({**identity(part), "event": e.event_type, "item": e.item_key, "created_at": e.created_at, "payload": json.dumps(e.payload)})
        elif mode == "runs":
            for r in db.query(CompetitionRun).filter_by(participation_id=part.id).order_by(CompetitionRun.id):
                rows.append({**identity(part), "run_id": r.id, "item": r.item_key, "kind": r.kind, "sql": r.sql, "created_at": r.created_at, "result": json.dumps(r.result)})
        elif mode == "survey":
            survey = db.get(CompetitionSurvey, part.id)
            if survey:
                rows.append({**identity(part), **survey.response, "updated_at": survey.updated_at})
    output = io.StringIO()
    columns = list(rows[0]) if rows else ["participant", "competition_id"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        # Avoid executing spreadsheet formulas in learner-entered narrative/SQL.
        writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
    return output.getvalue()
