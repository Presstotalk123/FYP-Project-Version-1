"""Wrap the Dify grading SSE stream and, on the 'done' event, insert
a lab_submissions row. Used by the unified lab ERD streaming submission endpoint."""

import json
import logging
from typing import Iterator, Optional

from sqlalchemy.orm import Session

from app.models.lab_submission import LabSubmission

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


def stream_with_lab_item_persistence(
    *,
    stream: Iterator[str],
    db: Session,
    lab_id: int,
    lab_item_id: int,
    user_id: int,
    session_id: int,
    submitted_xml: Optional[str],
    submitted_image_storage_key: Optional[str],
) -> Iterator[str]:
    """Forward every SSE chunk from `stream` to the caller. When a 'done' event
    arrives with a valid grading payload, insert a LabSubmission row using
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
                logger.warning("lab_erd_submission: malformed 'done' payload; skipping persist")
                continue
            structured = payload.get("structured_output") or {}
            score = structured.get("score") or {}
            try:
                earned = float(score.get("earned_points", 0) or 0)
                total = float(score.get("total_points", 0) or 0)
            except (TypeError, ValueError):
                logger.warning("lab_erd_submission: invalid earned/total; skipping persist")
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
            checks = structured.get("checks", [])
            sub = LabSubmission(
                lab_id=lab_id,
                lab_item_id=lab_item_id,
                lab_task_id=None,
                user_id=user_id,
                session_id=session_id,
                is_passed=1 if (percent or 0) >= 50 else 0,
                score_earned=earned,
                score_total=total,
                detail_json=json.dumps({
                    "label": label,
                    "checks": checks,
                    "submitted_xml": submitted_xml,
                    "image_key": submitted_image_storage_key,
                    "percent": percent,
                }, ensure_ascii=False),
            )
            db.add(sub)
            db.commit()
