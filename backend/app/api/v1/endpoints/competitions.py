"""Database Rescue student workflow and staff authoring APIs."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.models.user import User
from app.models.question import Question
from app.models.competition import (
    Competition, CompetitionSource, CompetitionIncident, CompetitionIncidentVersion,
    CompetitionParticipation, CompetitionSubmission, CompetitionReview,
    CompetitionSurvey,
)
from app.schemas.competition import (
    AdaptRequest, CompetitionWrite, DraftWrite, ImportRequest, IncidentWrite,
    ReviewRequest, RunRequest, SubmitRequest, WindowRequest,
    InspectionRequest, SurveyRequest,
)
from app.services import competition as service
from app.services.incident_authoring import normalise_source, adaptation, validate_document, PARSER_VERSION
from app.core.competition_executor import digest, execute, public_database

router = APIRouter(tags=["competitions"])
student = APIRouter(dependencies=[Depends(service.require_enabled)])
staff = APIRouter(prefix="/admin", dependencies=[Depends(require_staff_role)])


@router.get("/competitions/capabilities")
def capabilities(_user: User = Depends(get_current_user)):
    return {"enabled": settings.COMPETITIONS_ENABLED}


@student.get("/competitions")
def list_competitions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Competition).filter_by(published=1).order_by(Competition.id.desc()).all()
    result = []
    for comp in rows:
        if comp.config.get("class_groups") and (user.class_group or "").strip() not in comp.config["class_groups"]:
            continue
        part = db.query(CompetitionParticipation).filter_by(competition_id=comp.id, user_id=user.id).first()
        result.append({**service.metadata(comp), "participation_id": part.id if part else None, "phase": service.summary(db, part, comp)["phase"] if part else None})
    return result


@student.get("/competitions/{competition_id}")
def competition_detail(competition_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    comp = service.get_competition(db, competition_id, user)
    part = db.query(CompetitionParticipation).filter_by(competition_id=comp.id, user_id=user.id).first()
    return {**service.metadata(comp), "participation": service.summary(db, part, comp) if part else None,
            "leaderboard": service.leaderboard(db, comp, user)}


@student.post("/competitions/{competition_id}/join")
def join_competition(competition_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    part = service.join(db, competition_id, user)
    return {"participation_id": part.id}


@student.post("/competition-sessions/{part_id}/phases/{phase}/{action}")
def phase_action(part_id: int, phase: Literal["gameplay"], action: Literal["submit"],
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user_id = user.id
    service.participation(db, part_id, user, mutate=True)
    token = service.acquire(db, user_id)
    try:
        service.finish_phase(db, part_id, phase, user)
        part, comp = service.participation(db, part_id, user)
        return service.summary(db, part, comp)
    finally:
        service.release(db, user_id, token)


@student.get("/competition-sessions/{part_id}/items/{key}")
def get_item(part_id: int, key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.public_incident(db, part_id, key, user)


@student.put("/competition-sessions/{part_id}/items/{key}/draft")
def save_draft(part_id: int, key: str, body: DraftWrite, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.save_draft(db, part_id, key, user, body)


@student.post("/competition-sessions/{part_id}/items/{key}/runs")
def run_item(part_id: int, key: str, body: RunRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.run_sql(db, part_id, key, user, body)


@student.post("/competition-sessions/{part_id}/items/{key}/checks")
def check_item(part_id: int, key: str, body: RunRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.run_sql(db, part_id, key, user, body, check=True)


@student.post("/competition-sessions/{part_id}/items/{key}/help")
def item_help(part_id: int, key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.help_checkpoint(db, part_id, key, user)


@student.post("/competition-sessions/{part_id}/items/{key}/submissions")
def submit_item(part_id: int, key: str, body: SubmitRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.submit_report(db, part_id, key, user, body)


@student.post("/competition-sessions/{part_id}/items/{key}/inspections")
def inspect_item(part_id: int, key: str, body: InspectionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _part, _comp, version = service.item(db, part_id, key, user)
    doc = version.document
    if body.artifact_type == "component":
        valid = body.artifact_id in {c["id"] for c in doc["components"]}
    else:
        scenario = next(s for s in doc["scenarios"] if s["visible"])
        valid = body.artifact_id in {t["name"] for t in public_database(doc["schema_sql"], scenario["seed_sql"])}
    if not valid:
        service.fail("Artifact not found in this incident.", 404)
    service.event(db, part_id, "artifact_inspected", item_key=key, payload={**body.model_dump(), "incident_version_id": version.id})
    db.commit()
    return {"recorded": True}


@student.post("/competition-sessions/{part_id}/survey")
def survey(part_id: int, body: SurveyRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    part, comp = service.participation(db, part_id, user)
    if not service.summary(db, part, comp)["participation_complete"]:
        service.fail("The optional survey is available after all required reports are submitted.")
    row = db.get(CompetitionSurvey, part_id)
    if row:
        row.response = body.model_dump()
    else:
        db.add(CompetitionSurvey(participation_id=part_id, response=body.model_dump()))
    service.event(db, part_id, "survey_submitted")
    db.commit()
    return {"submitted": True}


def source_row(source):
    return {"id": source.id, "provider": source.provider, "external_id": source.external_id,
            "title": source.snapshot.get("title"), "eligible": source.snapshot.get("eligible", False),
            "authorised": bool(source.authorised), "diagnostics": source.diagnostics, "content_hash": source.content_hash}


def import_source(db, raw, user, authorised, *, provider="leetcode", external_id=None):
    if len(json.dumps(raw)) > 500_000:
        service.fail("Source entry exceeds the 500 KB authoring limit.", 413)
    external_id = str(external_id or raw.get("id", ""))[:100]
    if not external_id:
        service.fail("Every imported source needs a stable external ID.")
    try:
        content_hash = digest(raw)
    except (TypeError, ValueError):
        service.fail("Source records must contain finite, serialisable JSON values.")
    existing = db.query(CompetitionSource).filter_by(provider=provider, external_id=external_id, content_hash=content_hash).first()
    if existing:
        if authorised:
            existing.authorised = 1
            db.commit()
        return existing
    snapshot, diagnostics = normalise_source(raw)
    row = CompetitionSource(provider=provider, external_id=external_id, content_hash=content_hash, snapshot=snapshot,
                            diagnostics=diagnostics, authorised=int(authorised), created_by=user.id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(CompetitionSource).filter_by(provider=provider, external_id=external_id, content_hash=content_hash).one()
    return row


@staff.get("/competition-sources")
def sources(db: Session = Depends(get_db)):
    return [source_row(s) for s in db.query(CompetitionSource).order_by(CompetitionSource.id.desc()).all()]


@staff.get("/competition-sources/{source_id}")
def source_detail(source_id: int, db: Session = Depends(get_db)):
    source = db.get(CompetitionSource, source_id)
    if not source:
        service.fail("Source not found.", 404)
    return {**source_row(source), "snapshot": source.snapshot}


@staff.post("/competition-sources/import")
def import_sources(body: ImportRequest, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    if len(json.dumps(body.entries)) > 8_000_000:
        service.fail("Import sources in batches smaller than 8 MB.", 413)
    return [source_row(import_source(db, raw, user, body.authorised)) for raw in body.entries]


@staff.post("/competition-sources/from-question/{question_id}")
def import_question(question_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    question = db.get(Question, question_id)
    if not question or question.is_deleted or question.owner_assessment_id is not None or question.advanced_sql_testing:
        service.fail("Choose a master SELECT question from the question bank.")
    raw = {"id": question.leetcode_id or question.id, "question_id": question.id, "title": question.title,
           "description": question.description, "schema_sql": question.schema_sql, "sample_data_sql": question.sample_data_sql,
           "correct_answer_query": question.correct_answer_query}
    return source_row(import_source(db, raw, user, False, provider="question", external_id=question.id))


@staff.post("/competition-sources/{source_id}/authorise")
def authorise_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(CompetitionSource, source_id)
    if not source:
        service.fail("Source not found.", 404)
    source.authorised = 1
    db.commit()
    return source_row(source)


@staff.post("/competition-sources/{source_id}/adapt")
def adapt_source(source_id: int, body: AdaptRequest, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    source = db.get(CompetitionSource, source_id)
    if not source or not source.authorised:
        service.fail("Confirm that you are authorised to use this source before adapting it.")
    try:
        document = adaptation(source.snapshot, body.template, body.complaint, body.business_rules)
    except ValueError as exc:
        service.fail(str(exc))
    row = CompetitionIncident(source_id=source.id, title=document["title"], document=document, created_by=user.id)
    db.add(row)
    db.commit()
    return {"id": row.id}


def incident_row(row):
    return {"id": row.id, "title": row.title, "source_id": row.source_id, "status": row.status,
            "revision": row.revision, "document": row.document, "validation": row.validation}


@staff.get("/competition-incidents")
def incidents(db: Session = Depends(get_db)):
    return [{"id": r.id, "title": r.title, "status": r.status, "difficulty": r.document["difficulty"], "topic": r.document["topic"]}
            for r in db.query(CompetitionIncident).order_by(CompetitionIncident.id.desc()).all()]


@staff.post("/competition-incidents")
def create_incident(body: IncidentWrite, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    if body.source_id and not db.get(CompetitionSource, body.source_id):
        service.fail("Source not found.", 404)
    row = CompetitionIncident(source_id=body.source_id, title=body.document.title, document=body.document.model_dump(), created_by=user.id)
    db.add(row)
    db.commit()
    return incident_row(row)


@staff.get("/competition-incidents/{incident_id}")
def incident_detail(incident_id: int, db: Session = Depends(get_db)):
    row = db.get(CompetitionIncident, incident_id)
    if not row:
        service.fail("Incident not found.", 404)
    return incident_row(row)


@staff.put("/competition-incidents/{incident_id}")
def update_incident(incident_id: int, body: IncidentWrite, db: Session = Depends(get_db)):
    from sqlalchemy import update
    if body.source_id and not db.get(CompetitionSource, body.source_id):
        service.fail("Source not found.", 404)
    result = db.execute(update(CompetitionIncident).where(CompetitionIncident.id == incident_id, CompetitionIncident.revision == body.revision)
               .values(document=body.document.model_dump(), title=body.document.title, source_id=body.source_id,
                       revision=CompetitionIncident.revision + 1, status="draft", validation=None, validated_hash=None))
    if result.rowcount != 1:
        db.rollback()
        service.fail("Incident changed in another tab. Reload before saving.", 409)
    db.commit()
    return incident_row(db.get(CompetitionIncident, incident_id))


@staff.post("/competition-incidents/{incident_id}/validate")
def validate_incident(incident_id: int, db: Session = Depends(get_db)):
    row = db.get(CompetitionIncident, incident_id)
    if not row:
        service.fail("Incident not found.", 404)
    document, revision = row.document, row.revision
    db.commit()
    report = validate_document(document)
    from sqlalchemy import update
    result = db.execute(update(CompetitionIncident).where(CompetitionIncident.id == incident_id, CompetitionIncident.revision == revision)
               .values(validation=report, validated_hash=report["content_hash"] if report["valid"] else None,
                       status="validated" if report["valid"] else "needs_review"))
    if result.rowcount != 1:
        db.rollback()
        service.fail("Incident changed while validation ran. Validate the saved revision again.", 409)
    db.commit()
    return report


@staff.post("/competition-incidents/{incident_id}/approve")
def approve_incident(incident_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    row = db.query(CompetitionIncident).filter_by(id=incident_id).with_for_update().first()
    if not row or not row.validation or not row.validation.get("valid") or row.validated_hash != digest(row.document):
        service.fail("Validate the current document successfully before approving it.")
    if row.source_id and not db.get(CompetitionSource, row.source_id).authorised:
        service.fail("Confirm source authorisation before approval.")
    source = db.get(CompetitionSource, row.source_id) if row.source_id else None
    artifact_hash = digest({"document": row.document, "source_hash": source.content_hash if source else None, "parser_version": row.validation["parser_version"]})
    version = db.query(CompetitionIncidentVersion).filter_by(incident_id=row.id, content_hash=artifact_hash).first()
    if not version:
        version = CompetitionIncidentVersion(incident_id=row.id, content_hash=artifact_hash, document=row.document,
                                             source_id=row.source_id, parser_version=row.validation["parser_version"], approved_by=user.id)
        db.add(version)
        db.flush()
    row.status = "approved"
    db.commit()
    return {"version_id": version.id, "content_hash": version.content_hash, "parser_version": row.validation["parser_version"]}


@staff.get("/competition-incident-versions")
def versions(db: Session = Depends(get_db)):
    return [{"id": v.id, "incident_id": v.incident_id, "title": v.document["title"], "topic": v.document["topic"],
             "difficulty": v.document["difficulty"], "content_hash": v.content_hash} for v in db.query(CompetitionIncidentVersion).order_by(CompetitionIncidentVersion.id.desc())]


@staff.get("/competition-incident-versions/{version_id}")
def version_detail(version_id: int, db: Session = Depends(get_db)):
    version = db.get(CompetitionIncidentVersion, version_id)
    if not version:
        service.fail("Version not found.", 404)
    return {"id": version.id, "document": version.document, "content_hash": version.content_hash}


@staff.get("/competition-incidents/{incident_id}/preview")
def preview(incident_id: int, db: Session = Depends(get_db)):
    row = db.get(CompetitionIncident, incident_id)
    if not row:
        service.fail("Incident not found.", 404)
    doc = row.document
    scenario = next(s for s in doc["scenarios"] if s["visible"])
    return {"complaint": doc["complaint"], "business_rules": doc["business_rules"],
            "database": public_database(doc["schema_sql"], scenario["seed_sql"]),
            "features": [{"label": c["label"], "faulty": execute(doc["schema_sql"], scenario["seed_sql"], c["query"], preview=True),
                          "reference": execute(doc["schema_sql"], scenario["seed_sql"], c["reference_query"], preview=True)} for c in doc["components"]]}


def admin_competition(row):
    return {"id": row.id, "title": row.title, "description": row.description, "topic": row.topic, "config": service.competition_config(row),
            "published": bool(row.published), "opens_at": service.utc(row.opens_at), "closes_at": service.utc(row.closes_at),
            "content_hash": row.content_hash}


@staff.get("/competitions")
def admin_competitions(db: Session = Depends(get_db)):
    return [admin_competition(row) for row in db.query(Competition).order_by(Competition.id.desc())]


@staff.post("/competitions")
def create_competition(body: CompetitionWrite, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    row = Competition(title=body.title, description=body.description, topic=body.topic, config=body.config.model_dump(),
                      opens_at=service.utc(body.opens_at), closes_at=service.utc(body.closes_at), created_by=user.id)
    db.add(row)
    db.commit()
    return admin_competition(row)


@staff.get("/competitions/{competition_id}")
def admin_detail(competition_id: int, db: Session = Depends(get_db)):
    row = db.get(Competition, competition_id)
    if not row:
        service.fail("Competition not found.", 404)
    return admin_competition(row)


@staff.put("/competitions/{competition_id}")
def edit_competition(competition_id: int, body: CompetitionWrite, db: Session = Depends(get_db)):
    row = db.query(Competition).filter_by(id=competition_id).with_for_update().first()
    if not row or row.published:
        service.fail("Published competition content is frozen. Create a new competition to change it.")
    for key in ("title", "description", "topic", "opens_at", "closes_at"):
        value = getattr(body, key)
        setattr(row, key, service.utc(value) if key in {"opens_at", "closes_at"} else value)
    row.config = body.config.model_dump()
    db.commit()
    return admin_competition(row)


@staff.post("/competitions/{competition_id}/publish")
def publish_competition(competition_id: int, db: Session = Depends(get_db)):
    row = db.query(Competition).filter_by(id=competition_id).with_for_update().first()
    if not row:
        service.fail("Competition not found.", 404)
    if row.published:
        return admin_competition(row)
    config = row.config
    ids = config["missions"]
    versions = [db.get(CompetitionIncidentVersion, i) for i in ids]
    if any(v is None for v in versions):
        service.fail("Every competition item must be an approved incident version.")
    if len({v.incident_id for v in versions}) != len(versions):
        service.fail("Use each incident identity only once.")
    if any(v.document["topic"].lower() != row.topic.lower() for v in versions):
        service.fail("All incidents must match the competition topic.")
    schemas = [digest(v.document["schema_sql"]) for v in versions]
    if len(schemas) != len(set(schemas)):
        service.fail("Use distinct schemas for independent incidents.")
    row.content_hash = digest({"title": row.title, "topic": row.topic, "config": config, "versions": [v.content_hash for v in versions]})
    row.published = 1
    db.commit()
    return admin_competition(row)


@staff.put("/competitions/{competition_id}/window")
def window(competition_id: int, body: WindowRequest, db: Session = Depends(get_db)):
    row = db.get(Competition, competition_id)
    if not row:
        service.fail("Competition not found.", 404)
    row.opens_at, row.closes_at = service.utc(body.opens_at), service.utc(body.closes_at)
    db.commit()
    return admin_competition(row)


@staff.get("/competitions/{competition_id}/participants")
def participants(competition_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, competition_id)
    if not comp:
        service.fail("Competition not found.", 404)
    rows = db.query(CompetitionParticipation, User).join(User, User.id == CompetitionParticipation.user_id).filter(CompetitionParticipation.competition_id == competition_id).all()
    return [{**service.summary(db, part, comp), "name": user.name, "email": user.email, "cohort": part.cohort} for part, user in rows]


@staff.get("/competitions/{competition_id}/submissions")
def submissions(competition_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, competition_id)
    if not comp:
        service.fail("Competition not found.", 404)
    rows = db.query(CompetitionSubmission, CompetitionParticipation, User).join(CompetitionParticipation, CompetitionParticipation.id == CompetitionSubmission.participation_id).join(User, User.id == CompetitionParticipation.user_id).filter(CompetitionParticipation.competition_id == competition_id).order_by(CompetitionSubmission.id.desc()).all()
    result = []
    for submission, part, user in rows:
        if submission.item_key not in service.item_versions(part, comp):
            continue
        reviews = db.query(CompetitionReview).filter_by(submission_id=submission.id).order_by(CompetitionReview.id.desc()).all()
        document = db.get(CompetitionIncidentVersion, submission.incident_version_id).document
        result.append({"id": submission.id, "item": submission.item_key, "name": user.name or user.email, "cohort": part.cohort,
                       "payload": submission.payload, "status": submission.status, "result": submission.result, "help_level": submission.help_level,
                       "fault_cause": document["fault_cause"], "reference_query": next(c["reference_query"] for c in document["components"] if c["id"] == document["culprit_component"]),
                       "reviews": [{"diagnosis_score": r.diagnosis_score, "explanation_score": r.explanation_score, "rationale": r.rationale, "reviewer_id": r.reviewer_id, "created_at": r.created_at} for r in reviews]})
    return result


@staff.post("/competition-submissions/{submission_id}/reviews")
def review(submission_id: int, body: ReviewRequest, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    if not db.get(CompetitionSubmission, submission_id):
        service.fail("Submission not found.", 404)
    row = CompetitionReview(submission_id=submission_id, reviewer_id=user.id, **body.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id}


@staff.post("/competition-submissions/{submission_id}/retry")
def retry_judgement(submission_id: int, db: Session = Depends(get_db), staff_user: User = Depends(require_staff_role)):
    saved = db.get(CompetitionSubmission, submission_id)
    if not saved:
        service.fail("Submission not found.", 404)
    part = db.get(CompetitionParticipation, saved.participation_id)
    learner = db.get(User, part.user_id)
    request = SubmitRequest(request_key=saved.request_key, revision=saved.draft_revision)
    key, part_id, actor_id = saved.item_key, part.id, staff_user.id
    service.event(db, part_id, "staff_judge_retry", item_key=key, payload={"staff_id": actor_id, "submission_id": submission_id})
    db.commit()
    return service.submit_report(db, part_id, key, learner, request)


@staff.get("/competitions/{competition_id}/exports/{mode}")
def export(competition_id: int, mode: Literal["participation", "submissions", "outcomes", "events", "runs", "survey"], db: Session = Depends(get_db)):
    comp = db.get(Competition, competition_id)
    if not comp:
        service.fail("Competition not found.", 404)
    return Response(service.export_rows(db, comp, mode), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="competition-{competition_id}-{mode}.csv"'})


router.include_router(student)
router.include_router(staff)
