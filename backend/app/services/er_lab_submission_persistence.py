"""Wrap the Dify grading SSE stream and, on the 'done' event, insert
an er_lab_submissions row. Used only when the unified submission endpoint
is called in lab mode."""

import json
import logging
from datetime import datetime
from typing import Iterator, Optional

from sqlalchemy.orm import Session

from app.models.er_lab_submission import ErLabSubmission

logger = logging.getLogger(__name__)


def _parse_sse_event_block(block: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (event_name, data_json_str) from one SSE block, or (None, None)."""
    event_name: Optional[str] = None
    data_lines: list[str] = []
    for line in block.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    if not event_name:
        return None, None
    return event_name, "\n".join(data_lines) if data_lines else None


def stream_with_lab_persistence(
    *,
    stream: Iterator[str],
    db: Session,
    er_lab_id: int,
    er_lab_question_id: int,
    user_id: int,
    session_id: int,
    submitted_xml: Optional[str],
    submitted_image_storage_key: Optional[str],
) -> Iterator[str]:
    """Forward every SSE chunk from `stream` to the caller. When a 'done' event
    arrives with a valid grading payload, insert an ErLabSubmission row using
    the auto-grade snapshot.

    On 'error' events, partial streams, or malformed payloads: no row is
    inserted. The caller's UX shows the error; the next submission gets a
    fresh row when grading succeeds.
    """
    buffer = ""
    for chunk in stream:
        yield chunk
        buffer += chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            event_name, data_str = _parse_sse_event_block(block)
            if event_name != "done" or not data_str:
                continue
            try:
                payload = json.loads(data_str)
            except (json.JSONDecodeError, ValueError):
                logger.warning("er_lab_persistence: malformed 'done' payload; skipping persist")
                continue
            structured = payload.get("structured_output") or {}
            score = structured.get("score") or {}
            try:
                earned = float(score.get("earned_points", 0) or 0)
                total = float(score.get("total_points", 0) or 0)
            except (TypeError, ValueError):
                logger.warning("er_lab_persistence: invalid earned/total; skipping persist")
                continue
            percent_raw = score.get("percent", 0)
            try:
                if isinstance(percent_raw, str):
                    percent = float(percent_raw.rstrip("%"))
                else:
                    percent = float(percent_raw)
            except (TypeError, ValueError):
                percent = 0.0
            label = str(score.get("label", ""))
            sub = ErLabSubmission(
                er_lab_question_id=er_lab_question_id,
                er_lab_id=er_lab_id,
                user_id=user_id,
                session_id=session_id,
                submitted_xml=submitted_xml,
                submitted_image_storage_key=submitted_image_storage_key,
                auto_score_earned=earned,
                auto_score_total=total,
                auto_score_percent=percent,
                auto_score_label=label,
                auto_checks_json=json.dumps(structured.get("checks", []), ensure_ascii=False),
                auto_graded_at=datetime.utcnow(),
            )
            db.add(sub)
            db.commit()
