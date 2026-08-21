"""Grade students' saved ERD drafts on their behalf and record the results.

Why this exists: when the assessment timer ends, the frontend closes the
session and redirects. It never submits the ERD. A student who built a diagram
but did not click Submit therefore gets no grade, even though the canvas itself
survives in ``er_diagram_drafts``. This script replays the submit that never
happened. It feeds each saved draft through the same LangGraph submit graph the
live endpoint uses, then writes the same rows that endpoint writes: the
conversation score (which the assessment mark reads) and the analytics row.

Run it from ``backend/`` with the venv active. Nothing is written without
``--commit``.

One student, one question:

    python scripts/grade_saved_draft.py --user-id 137 --question-id 33
    python scripts/grade_saved_draft.py --user-id 137 --question-id 33 --commit

Every ungraded draft in one assessment:

    python scripts/grade_saved_draft.py --assessment-id 33
    python scripts/grade_saved_draft.py --assessment-id 33 --commit

``--question-id`` is the id the student attempted. For an assessment that is
the *clone* (``assessment_items.item_id``), not the bank question.
``--assessment-id`` resolves the clones for you.

Students who already have a grade are skipped, so the script is safe to re-run.
``--regrade`` includes them.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.assessment_item import AssessmentItem  # noqa: E402
from app.models.er_diagram_draft import ErDiagramDraft  # noqa: E402
from app.models.er_diagram_question import ERDiagramQuestion  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import er_staff_submission  # noqa: E402


def _grade_one(db, *, user, question, xml_text, commit, note, regrade):
    """Grade one draft through the shared service. Returns a status string.

    The grading and persistence live in app/services/er_staff_submission.py, which
    the staff endpoint also calls. This script only decides *what* to grade and
    prints the outcome.
    """
    try:
        # asyncio.run belongs here, at the script's top level, where blocking is correct.
        result = asyncio.run(er_staff_submission.grade_and_record(
            db,
            user_id=user.id,
            question=question,
            xml_text=xml_text,
            source="draft",
            on_grading_start=lambda: print(
                "    grading %d chars. This takes 30-90 seconds." % len(xml_text)
            ),
            # No staff member is behind a script run; the reason still records why.
            staff_id=None,
            reason=note,
            regrade=regrade,
            commit=commit,
        ))
    except er_staff_submission.AlreadyGraded:
        return "skipped (already graded)"
    except er_staff_submission.NoDiagram as exc:
        return "skipped (%s)" % exc
    except er_staff_submission.GradingFailed:
        return "FAILED (no done event)"

    summary = "%s %s%%" % (result.score.get("label"), result.score.get("percent"))
    print("    " + summary)
    return summary + (" (written)" if commit else " (dry run, not written)")


def _targets_for_assessment(db, assessment_id):
    """Every (user, question, xml) pair with a saved draft in this assessment."""
    question_ids = [
        row[0] for row in
        db.query(AssessmentItem.item_id)
        .filter(AssessmentItem.assessment_id == assessment_id,
                AssessmentItem.item_type == "er_question")
        .all()
    ]
    if not question_ids:
        print("Assessment %d has no er_question items." % assessment_id)
        return []

    print("ER questions in assessment %d: %s" % (assessment_id, question_ids))
    return (
        db.query(User, ERDiagramQuestion, ErDiagramDraft.xml)
        .join(ErDiagramDraft, ErDiagramDraft.user_id == User.id)
        .join(ERDiagramQuestion,
              ERDiagramQuestion.id == ErDiagramDraft.er_diagram_question_id)
        .filter(ErDiagramDraft.er_diagram_question_id.in_(question_ids),
                ERDiagramQuestion.is_deleted == 0)
        .order_by(User.email, ERDiagramQuestion.id)
        .all()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--question-id", type=int, default=None)
    parser.add_argument("--assessment-id", type=int, default=None,
                        help="Grade every saved draft for this assessment's ER questions.")
    parser.add_argument("--xml-file", type=Path, default=None,
                        help="Grade this .drawio file instead of the stored draft. "
                             "Single-student mode only.")
    parser.add_argument("--note", type=str, default=None,
                        help="Text stored on the submission row, e.g. "
                             "'graded from autosaved draft by staff'. Not sent to the grader.")
    parser.add_argument("--regrade", action="store_true",
                        help="Include students who already have a grade.")
    parser.add_argument("--commit", action="store_true",
                        help="Write the grades. Without it nothing is saved.")
    args = parser.parse_args()

    if settings.ERD_TUTOR_ENGINE != "langgraph":
        print("ERD_TUTOR_ENGINE is %r, not 'langgraph'. Stop." % settings.ERD_TUTOR_ENGINE)
        return 2

    if args.assessment_id is None and (args.user_id is None or args.question_id is None):
        print("Give either --assessment-id, or both --user-id and --question-id.")
        return 2
    if args.assessment_id is not None and args.xml_file is not None:
        print("--xml-file works in single-student mode only.")
        return 2

    db = SessionLocal()
    try:
        if args.assessment_id is not None:
            targets = _targets_for_assessment(db, args.assessment_id)
        else:
            user = db.query(User).filter(User.id == args.user_id).first()
            if user is None:
                print("No user with id %d." % args.user_id)
                return 1
            question = (
                db.query(ERDiagramQuestion)
                .filter(ERDiagramQuestion.id == args.question_id,
                        ERDiagramQuestion.is_deleted == 0)
                .first()
            )
            if question is None:
                print("No ER question with id %d." % args.question_id)
                return 1
            if args.xml_file is not None:
                xml = args.xml_file.read_text(encoding="utf-8-sig")
            else:
                draft = (
                    db.query(ErDiagramDraft)
                    .filter(ErDiagramDraft.user_id == args.user_id,
                            ErDiagramDraft.er_diagram_question_id == args.question_id)
                    .first()
                )
                if draft is None:
                    print("No saved draft for that user and question. Nothing to grade.")
                    return 1
                xml = draft.xml
            targets = [(user, question, xml)]

        if not targets:
            print("Nothing to grade.")
            return 1

        print("mode      : %s" % ("COMMIT" if args.commit else "DRY RUN"))
        print("targets   : %d" % len(targets))
        print("")

        results = []
        for user, question, xml in targets:
            xml_text = (xml or "").strip()
            label = "%s / q%d %s" % (user.email, question.id, question.title)
            print(label)
            if not xml_text:
                print("    empty draft, skipped")
                results.append((label, "skipped (empty draft)"))
                continue
            try:
                status = _grade_one(
                    db, user=user, question=question, xml_text=xml_text,
                    commit=args.commit, note=args.note, regrade=args.regrade,
                )
            except Exception as exc:  # one bad draft must not stop the sweep
                db.rollback()
                status = "FAILED (%s)" % exc
                print("    " + status)
            results.append((label, status))

        print("")
        print("SUMMARY")
        for label, status in results:
            print("  %-60s %s" % (label[:60], status))
        if not args.commit:
            print("")
            print("Dry run. Nothing was written. Re-run with --commit to save.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
