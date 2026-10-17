"""Adaptive scaffolding engine (Phase 4).

A small, bidirectional state machine over four fading-support levels, tracked per
(student, concept) on ConceptMastery. Support fades as a student strings together
successes and is restored when they start failing, so a struggling student is never
stranded at ``independent``. Because the level lives on the concept rather than the
tutor conversation, it carries across every question exercising that concept.

Transitions are evaluated once per graded submission (``apply_attempt_transition``,
called by the Learner Profiling Agent), and a transition consumes the streak that
triggered it, so 3 successes fade support by exactly one level. Chat turns and the
indicator only read the level (``level_for_concept``).

The core ``compute_next_level`` is pure (no DB, no LLM) and directly unit-testable.
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

# Upper mastery_level bounds for seeding a level when none is stored yet (rows that
# predate per-concept scaffolding). Aligned with lad_service.mastery_band:
# novice -> full, developing -> guided, proficient -> minimal, mastered -> independent.
_MASTERY_SEED_BOUNDS = [(0.25, "full"), (0.5, "guided"), (0.8, "minimal")]


def level_from_mastery(mastery_level: Optional[float]) -> str:
    """Starting level implied by a 0..1 mastery value."""
    if mastery_level is None:
        return DEFAULT_LEVEL
    for bound, level in _MASTERY_SEED_BOUNDS:
        if mastery_level < bound:
            return level
    return "independent"


def current_level(mastery: Optional[ConceptMastery]) -> str:
    """Stored level for a mastery row, seeded from mastery_level when unset."""
    if mastery is None:
        return DEFAULT_LEVEL
    if mastery.scaffolding_level in LEVELS:
        return mastery.scaffolding_level
    return level_from_mastery(mastery.mastery_level)


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


def apply_attempt_transition(mastery: ConceptMastery) -> Tuple[str, str, bool]:
    """Apply the transition rule to a mastery row whose streaks were just updated.

    Persists the level on the row (seeding it if unset) and, on a transition, resets
    the streak that triggered it so the next step needs a fresh streak. Does not
    commit — the caller owns the session. Returns (previous_level, new_level, changed).
    """
    prev = current_level(mastery)
    new, changed = compute_next_level(
        prev, mastery.consecutive_successes, mastery.consecutive_failures
    )
    mastery.scaffolding_level = new
    if changed:
        if LEVELS.index(new) > LEVELS.index(prev):
            mastery.consecutive_successes = 0
        else:
            mastery.consecutive_failures = 0
    return prev, new, changed


def level_for_concept(db: Session, user_id: int, concept_id: Optional[int]) -> str:
    """Read-only: the student's current level on ``concept_id`` (default if none)."""
    if concept_id is None:
        return DEFAULT_LEVEL
    mastery = (
        db.query(ConceptMastery)
        .filter(
            ConceptMastery.user_id == user_id,
            ConceptMastery.concept_id == concept_id,
        )
        .first()
    )
    return current_level(mastery)
