"""One-off backfill: populate assessment_sessions.weighted_score for sessions that were
finalized before the persisted-score change shipped.

Sessions finalized before the weighted_score column existed have it NULL even though
attempt_complete=1, and single-attempt assessments never re-finalize (so the value would
otherwise stay NULL forever and readers would show "N/A"). This script recomputes the
score once per such session via assessment_scoring.compute_weighted_score and writes it.

Run AFTER run_assessment_session_weighted_score_migration.py. Idempotent: it only touches
rows where attempt_complete=1 and weighted_score IS NULL, so re-running is safe and a no-op
once everything is populated.
"""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models.assessment import Assessment
from app.models.assessment_session import AssessmentSession
from app.services import assessment_scoring


def run() -> None:
    db = SessionLocal()
    try:
        sessions = (
            db.query(AssessmentSession)
            .filter(
                AssessmentSession.attempt_complete == 1,
                AssessmentSession.weighted_score.is_(None),
            )
            .all()
        )
        print(f"Found {len(sessions)} finalized session(s) with no persisted weighted_score.")

        # Cache assessments so we don't re-query the same one per session.
        assessments: dict[int, Assessment | None] = {}
        updated = 0
        skipped = 0
        for s in sessions:
            if s.assessment_id not in assessments:
                assessments[s.assessment_id] = (
                    db.query(Assessment).filter(Assessment.id == s.assessment_id).first()
                )
            assessment = assessments[s.assessment_id]
            if assessment is None:
                skipped += 1
                continue
            # None when the assessment carries no weightage — leave the column NULL.
            s.weighted_score = assessment_scoring.compute_weighted_score(
                db, assessment, s.user_id
            )
            updated += 1

        db.commit()
        print(f"[OK] Updated {updated} session(s); skipped {skipped} (assessment missing).")
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Backfill: assessment_sessions.weighted_score")
    print("=" * 60)
    run()
    print("Done.")
