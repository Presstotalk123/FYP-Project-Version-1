"""Adaptive scaffolding engine (Phase 4).

A small, bidirectional state machine over four fading-support levels, tracked per
active concept. Support fades as a student strings together successes and is
restored when they start failing, so a struggling student is never stranded at
``independent``.

The core ``compute_next_level`` is pure (no DB, no LLM) and directly unit-testable.
``evaluate_for_concept`` applies it against a student's ConceptMastery streaks and
persists/logs any transition.
"""
import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.concept_mastery import ConceptMastery

logger = logging.getLogger(__name__)

# Ordered from most support to least. Index = independence rank.
LEVELS = ["full", "guided", "minimal", "independent"]
DEFAULT_LEVEL = "full"


def compute_next_level(
    current_level: str,
    consecutive_successes: int,
    consecutive_failures: int,
) -> Tuple[str, bool]:
    """Return (next_level, changed).

    Upgrade (fade support) one step when successes reach SCAFFOLDING_UPGRADE_STREAK;
    downgrade (restore support) one step when failures reach SCAFFOLDING_DOWNGRADE_STREAK.
    Failures take precedence over successes (they can't both be non-zero in practice,
    since the profiling agent zeroes one when it increments the other). Clamped to
    the ends of LEVELS.
    """
    try:
        idx = LEVELS.index(current_level)
    except ValueError:
        idx = 0  # unknown/legacy value -> treat as "full"

    new_idx = idx
    if consecutive_failures >= settings.SCAFFOLDING_DOWNGRADE_STREAK:
        new_idx = max(0, idx - 1)
    elif consecutive_successes >= settings.SCAFFOLDING_UPGRADE_STREAK:
        new_idx = min(len(LEVELS) - 1, idx + 1)

    return LEVELS[new_idx], new_idx != idx


def evaluate_for_concept(
    db: Session,
    user_id: int,
    concept_id: Optional[int],
    current_level: str,
) -> Tuple[str, bool]:
    """Compute the scaffolding level for ``user_id`` on ``concept_id``.

    Reads the student's ConceptMastery streaks for the concept and applies
    ``compute_next_level``. Returns (level, changed). Does not itself persist the
    conversation row — the caller owns that — but this is the single place the
    transition rule is applied against live mastery data.
    """
    if concept_id is None:
        return current_level, False

    mastery = (
        db.query(ConceptMastery)
        .filter(
            ConceptMastery.user_id == user_id,
            ConceptMastery.concept_id == concept_id,
        )
        .first()
    )
    if mastery is None:
        return current_level, False

    return compute_next_level(
        current_level,
        mastery.consecutive_successes,
        mastery.consecutive_failures,
    )
