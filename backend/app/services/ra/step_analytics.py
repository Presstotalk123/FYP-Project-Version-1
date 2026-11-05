"""How far students got in a multi-step part, for the staff analytics' details view.

The analytics stay one row per question and part; a multi-step part's row also carries
this breakdown, which staff open under "Details": for each step, how many students
reached it (their best Submit earned it), how many of those only through carry-forward,
and how many didn't. A student's best Submit is the one with the most marks (the latest
of equals), the one their score comes from.
"""
import json
from typing import Dict, Iterable, List, Optional, Tuple

from app.models.ra_question_part import RAQuestionPart


def step_marks(result_json: Optional[str], marks_earned: Optional[int]) -> Optional[List[dict]]:
    """The per-step marking stored with a multi-step attempt (None for other attempts)."""
    if marks_earned is None or not result_json:
        return None
    try:
        marking = (json.loads(result_json) or {}).get("marking")
    except (TypeError, ValueError):
        return None
    return (marking or {}).get("steps")


def part_steps(part: RAQuestionPart, by_user_part: Dict[Tuple[int, int], list], users: Iterable[int]
               ) -> Optional[List[dict]]:
    """[{index, name, prompt, marks, reached, carried, missed}] for a multi-step part, else None."""
    if not part.steps_json:
        return None
    steps = json.loads(part.steps_json)
    out = [{"index": i, "name": s.get("name"), "prompt": s.get("prompt") or "", "marks": s.get("marks") or 0,
            "reached": 0, "carried": 0, "missed": 0} for i, s in enumerate(steps)]
    for uid in users:
        attempts = [a for a in by_user_part.get((uid, part.id), []) if a.step_marks]
        if not attempts:
            continue
        best = max(reversed(attempts), key=lambda a: a.marks_earned or 0)   # most marks, latest of equals
        for i, row in enumerate(out):
            mark = best.step_marks[i] if i < len(best.step_marks) else None
            status = (mark or {}).get("status")
            if status in ("full", "reached"):
                row["reached"] += 1
            elif status == "carried":
                row["reached"] += 1
                row["carried"] += 1
            else:
                row["missed"] += 1
    return out
