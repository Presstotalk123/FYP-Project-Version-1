"""Grade a diagram on a student's behalf and record it as a real submission.

Staff reach this through the endpoint in api/v1/endpoints/er_analytics.py; the
maintenance script scripts/grade_saved_draft.py reaches the same code for bulk
cleanup. Keeping one implementation is the point: a submission written by either
route must be indistinguishable from a student's own, or the assessment mark and
the analytics disagree about what happened.

Every write here mirrors the live SSE persistence block in
api/v1/endpoints/er_diagram.py (`_persist`). If that block changes, change this.

`grade_and_record` is async on purpose. Nearly all of its 30-90 s is spent awaiting
the LLM over HTTP; a sync version would pin a threadpool worker for that whole wait.
The blocking SQLAlchemy writes are pushed to a worker thread instead, so the event
loop stays free in both directions.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.cache import Ns, bump_version
from app.models.er_diagram_draft import ErDiagramDraft
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.er_submission import ErSubmission
from app.services import assessment_scoring
from app.services.erd_tutor import persistence as erd_persistence
from app.services.erd_tutor import runner as erd_runner

logger = logging.getLogger(__name__)


class NoDiagram(Exception):
    """No usable diagram was given, or the named draft does not exist."""


class AlreadyGraded(Exception):
    """A grade exists and the caller did not ask to replace it."""


class GradingFailed(Exception):
    """The pipeline produced no done event. Nothing was written."""


@dataclass
class GradeResult:
    submission_id: Optional[int]
    score: dict
    source: str
    student_message: str


def _flt(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_draft(db: Session, *, user_id: int, question_id: int) -> ErDiagramDraft:
    """The student's autosaved canvas row for one question.

    Frozen at the moment their session closed: the draft write endpoint requires an
    active session in a running assessment, so a draft cannot be edited after the
    timer ends (see er_diagram.py::_er_question_accessible_via_assessment).
    """
    draft = (
        db.query(ErDiagramDraft)
        .filter(
            ErDiagramDraft.user_id == user_id,
            ErDiagramDraft.er_diagram_question_id == question_id,
        )
        .first()
    )
    if draft is None or not (draft.xml or "").strip():
        raise NoDiagram("No saved draft for this student and question.")
    return draft


def load_draft_xml(db: Session, *, user_id: int, question_id: int) -> str:
    """Just the canvas XML. See ``load_draft``."""
    return load_draft(db, user_id=user_id, question_id=question_id).xml.strip()


async def _collect_done(
    *, question, xml_text, image_bytes, ibl_stage, hint_level, last_report,
    submission_description: Optional[str] = None,
) -> Optional[dict]:
    """Drive the submit stream and return its ``done`` payload, or None.

    The runner emits SSE text rather than objects, so the terminal event is parsed
    back out here — the same shape the live passthrough wrapper reads.

    ``submission_description`` stays None for staff-added grades (the staff reason
    is a note, not evidence). The regrade service passes the student's stored
    description through, because it fed the original grade and must feed the replay.
    """
    stream = erd_runner.stream_er_submission_grading(
        question_id=question.id,
        problem_statement=question.problem_statement,
        difficulty_label=question.difficulty_label,
        rubric_json=question.rubric_json,
        submission_xml_text=xml_text,
        image_bytes=image_bytes,
        ibl_stage=ibl_stage,
        hint_level=hint_level,
        last_submit_report=last_report,
        submission_description=submission_description,
    )

    buffer = ""
    done_payload = None
    async for chunk in stream:
        buffer += chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            event_name = None
            data_lines = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
            if not data_lines:
                continue
            try:
                payload = json.loads("\n".join(data_lines))
            except (json.JSONDecodeError, ValueError):
                continue
            if event_name == "done":
                done_payload = payload
            elif event_name == "error":
                logger.warning(
                    "er_staff_submission: pipeline error question_id=%s detail=%s",
                    question.id,
                    payload.get("detail"),
                )
    return done_payload


async def grade_and_record(
    db: Session,
    *,
    user_id: int,
    question: ERDiagramQuestion,
    xml_text: Optional[str],
    image_bytes: Optional[bytes] = None,
    image_storage_key: Optional[str] = None,
    source: str,
    staff_id: Optional[int],
    reason: Optional[str],
    regrade: bool = False,
    commit: bool = True,
    on_grading_start=None,
) -> GradeResult:
    """Grade one diagram for one student. With ``commit=False`` nothing is written.

    ``on_grading_start`` fires once the decision to grade is final, just before the
    30-90 s LLM run. The script uses it for progress output; without it a skipped
    student would still be announced as "grading".
    """
    if not (xml_text or "").strip() and not image_bytes:
        raise NoDiagram("Give either diagram XML or an image.")

    conversation = erd_persistence.get_or_create_conversation(
        db,
        user_id=user_id,
        context_type="standalone",
        er_diagram_question_id=question.id,
    )
    state = erd_persistence.loaded_state(conversation)
    if state["last_submit_score"] and not regrade:
        raise AlreadyGraded("This student already has a grade for this question.")

    if on_grading_start is not None:
        on_grading_start()

    done = await _collect_done(
        question=question,
        xml_text=xml_text,
        image_bytes=image_bytes,
        ibl_stage=state["ibl_stage"],
        hint_level=state["hint_level"],
        last_report=state["last_submit_report"],
    )
    if done is None:
        raise GradingFailed("The grading pipeline produced no result.")

    structured = done.get("structured_output") or {}
    score = structured.get("score") or {}
    student_message = str(done.get("text") or "")

    if not commit:
        return GradeResult(
            submission_id=None, score=score, source=source, student_message=student_message
        )

    def _persist() -> int:
        ibl = structured.get("ibl") or {}
        next_hint = ibl.get("next_hint_level")
        save_fields = dict(
            ibl_stage=ibl.get("next_stage") or conversation.ibl_stage,
            hint_level=next_hint if isinstance(next_hint, int) else conversation.hint_level,
            last_submit_report=structured,
            last_submit_score=score,
        )
        # Only overwrite the canonical model when the pipeline extracted something,
        # so a failed parse does not clobber the last good one.
        canonical = done.get("canonical_erd") or {}
        if canonical.get("entities") or canonical.get("relationships"):
            save_fields["current_erd_model"] = canonical
        erd_persistence.save_state(db, conversation, **save_fields)

        checks = structured.get("checks")
        row = ErSubmission(
            user_id=user_id,
            er_diagram_question_id=question.id,
            score_earned=_flt(score.get("earned_points")),
            score_total=_flt(score.get("total_points")),
            score_percent=_flt(score.get("percent")),
            score_label=(str(score.get("label") or "").strip() or None),
            checks_json=(
                json.dumps(checks, ensure_ascii=False) if isinstance(checks, list) else None
            ),
            submitted_image_storage_key=image_storage_key,
            submitted_xml=xml_text,
            # The reason is stored, never graded: submission_description feeds
            # description_claims and would change the score.
            submission_description=None,
            hint_level_at_submit=state["hint_level"],
            ibl_stage_at_submit=state["ibl_stage"],
            added_by_staff_id=staff_id,
            added_reason=reason,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        erd_persistence.append_message(
            db, conversation, role="submission", mode="submit", content=student_message
        )

        # An ErdTutorConversation write deliberately does NOT invalidate the
        # materialized assessment averages (see core/cache.py) — only stop_assessment
        # and a staff reset bump that namespace. Without this bump the students page
        # keeps showing the old mark.
        bump_version(db, Ns.ASSESSMENT_ANALYTICS)
        # A late mark changes the student's assessment total, which the staff panel
        # reads from a value frozen at finalization. Shared with the override path.
        assessment_scoring.refresh_frozen_weighted_score(
            db, er_question_id=question.id, user_id=user_id
        )
        db.commit()
        return row.id

    # SQLAlchemy is blocking. Off the event loop it goes, exactly as the live
    # persistence hook does at er_diagram.py:1501.
    submission_id = await asyncio.to_thread(_persist)

    return GradeResult(
        submission_id=submission_id, score=score, source=source, student_message=student_message
    )
