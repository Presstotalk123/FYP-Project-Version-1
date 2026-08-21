"""Recompute the stored assessment total for every finished attempt.

`AssessmentSession.weighted_score` is computed once at finalization and never again,
and the staff activity panel reads that frozen value. Any change to how a mark is
derived therefore leaves it stale: the roster table recomputes and moves, the panel
does not, and the two disagree about the same student.

Run this once after such a change. It was written for the switch from "the latest ER
attempt" to "the best ER attempt", which can only raise a mark, but nothing here is
specific to that: it simply re-derives every stored total from current rules.

Run it from ``backend/``. Nothing is written without ``--commit``:

    python scripts/backfill_weighted_scores.py
    python scripts/backfill_weighted_scores.py --commit

Restrict it with ``--assessment-id`` when you only want one paper.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.cache import Ns, bump_version  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.assessment import Assessment  # noqa: E402
from app.models.assessment_session import AssessmentSession  # noqa: E402
from app.services import assessment_scoring  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment-id", type=int, default=None,
                        help="Only this assessment. Default: every one.")
    parser.add_argument("--commit", action="store_true",
                        help="Write the new totals. Without it nothing is saved.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(AssessmentSession).filter(AssessmentSession.attempt_complete == 1)
        if args.assessment_id is not None:
            query = query.filter(AssessmentSession.assessment_id == args.assessment_id)
        sessions = query.order_by(AssessmentSession.assessment_id, AssessmentSession.user_id).all()

        if not sessions:
            print("No finished sessions match. Nothing to do.")
            return 0

        # One lookup per assessment rather than per session: a cohort shares its paper.
        assessments: dict[int, Assessment] = {}
        changed = []
        unchanged = 0

        print("mode      : %s" % ("COMMIT" if args.commit else "DRY RUN"))
        print("sessions  : %d" % len(sessions))
        print("")

        for session in sessions:
            assessment = assessments.get(session.assessment_id)
            if assessment is None:
                assessment = (
                    db.query(Assessment)
                    .filter(Assessment.id == session.assessment_id)
                    .first()
                )
                if assessment is None:
                    continue
                assessments[session.assessment_id] = assessment

            fresh = assessment_scoring.compute_weighted_score(db, assessment, session.user_id)
            if fresh == session.weighted_score:
                unchanged += 1
                continue

            changed.append((session, session.weighted_score, fresh))
            if args.commit:
                session.weighted_score = fresh

        for session, before, after in changed:
            print("  assessment %-4s user %-5s  %s -> %s" % (
                session.assessment_id,
                session.user_id,
                "none" if before is None else before,
                "none" if after is None else after,
            ))

        if args.commit and changed:
            # The roster table reads a cached per-student score; without this bump it
            # would keep serving the old numbers alongside the new stored ones.
            bump_version(db, Ns.ASSESSMENT_ANALYTICS)
            db.commit()

        print("")
        print("changed   : %d" % len(changed))
        print("unchanged : %d" % unchanged)
        if not args.commit:
            print("")
            print("Dry run. Nothing was written. Re-run with --commit to save.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
