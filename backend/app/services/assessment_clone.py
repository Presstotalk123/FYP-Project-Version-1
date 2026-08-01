"""
Assessment content cloning — the mechanism that isolates per-assessment student
progress/attempts/history.

When an assessment is PUBLISHED, each referenced Question / Lab (+ tasks) / ER-question
is deep-copied into an *assessment-owned clone* (marked with `owner_assessment_id`), and
the `AssessmentItem.item_id` is repointed to the clone. Because every clone has a distinct
primary key, all existing grading/progress/attempt/cleanup/aggregation logic keeps working
unchanged and is automatically scoped to that one assessment. The published assessment is
thereby frozen: later edits to the master bank content do not affect it.

On unpublish/delete the clones are torn down — the heavy SQLite files are physically
removed but the rows are *soft-deleted* (is_deleted=1, owner_assessment_id kept) so that
history endpoints which INNER JOIN the content table still resolve a student's past attempts.

Functions here operate on an open Session and flush but do NOT commit; the calling endpoint
owns the transaction. On failure they raise so the caller can roll the whole publish back.
"""
import os
import shutil

from sqlalchemy.orm import Session

from app.models.question import Question
from app.models.lab import Lab
from app.models.lab_task import LabTask
from app.models.er_diagram_question import ERDiagramQuestion
from app.utils.db_generator import (
    generate_unique_filename,
    get_question_db_path,
    delete_question_database,
)
from app.utils.lab_db_manager import get_lab_template_path, delete_lab_template
from app.utils.lab_cleanup import terminate_all_lab_sessions


class AssessmentCloneError(Exception):
    """Raised when cloning assessment content fails; caller should roll back."""
    pass


def _copy_file(src: str, dst: str) -> None:
    """Copy a SQLite file, tracking dst so partial work can be cleaned up on rollback."""
    shutil.copy2(src, dst)


def clone_question_for_assessment(db: Session, question_id: int, assessment_id: int) -> int:
    """
    Deep-copy a master SQL question into an assessment-owned clone.

    The question's SQLite file is file-copied (not regenerated) so the copied
    correct_answer_hash stays valid without re-running validation.

    Returns the new clone question id. Raises AssessmentCloneError on failure.
    """
    master = db.query(Question).filter(
        Question.id == question_id,
        Question.is_deleted == 0,
    ).first()
    if not master:
        raise AssessmentCloneError(f"SQL question {question_id} not found for cloning")

    new_db_filename = generate_unique_filename()
    src_path = get_question_db_path(master.db_file_path)
    dst_path = get_question_db_path(new_db_filename)
    if not os.path.exists(src_path):
        raise AssessmentCloneError(
            f"SQLite file missing for question {question_id}: {src_path}"
        )
    _copy_file(src_path, dst_path)

    try:
        clone = Question(
            title=master.title,
            description=master.description,
            difficulty=master.difficulty,
            db_file_path=new_db_filename,
            correct_answer_hash=master.correct_answer_hash,
            correct_answer_query=master.correct_answer_query,
            schema_sql=master.schema_sql,
            sample_data_sql=master.sample_data_sql,
            advanced_sql_testing=master.advanced_sql_testing,
            test_script=master.test_script,
            check_query=master.check_query,
            created_by=master.created_by,
            is_deleted=0,
            owner_assessment_id=assessment_id,
        )
        db.add(clone)
        db.flush()
        return clone.id
    except Exception:
        # Best-effort cleanup of the copied file so a rollback leaves no orphan.
        if os.path.exists(dst_path):
            try:
                os.remove(dst_path)
            except OSError:
                pass
        raise


def clone_lab_for_assessment(db: Session, lab_id: int, assessment_id: int) -> int:
    """
    Deep-copy a master lab (SQL or graph) plus its non-deleted tasks into an
    assessment-owned clone. The template DB file is file-copied so task
    correct_answer_hashes stay valid. Student submissions are NOT copied.

    Returns the new clone lab id. Raises AssessmentCloneError on failure.
    """
    master = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0,
    ).first()
    if not master:
        raise AssessmentCloneError(f"Lab {lab_id} not found for cloning")

    clone = Lab(
        title=master.title,
        description=master.description,
        is_published=0,
        is_running=0,
        hide_correctness=master.hide_correctness,
        disable_ai_assist=master.disable_ai_assist,
        # Placeholder; rewritten to the clone-id-based filename after we get an id.
        template_db_path=master.template_db_path,
        schema_sql=master.schema_sql,
        sample_data_sql=master.sample_data_sql,
        lab_type=master.lab_type,
        created_by=master.created_by,
        is_deleted=0,
        owner_assessment_id=assessment_id,
    )
    db.add(clone)
    db.flush()  # obtain clone.id

    # Template DB filename is derived from the lab id (lab_{id}_template.db), so copy
    # the master template into the clone's id-based path. Works for sql and graph labs.
    src_path = get_lab_template_path(master.id)
    dst_path = get_lab_template_path(clone.id)
    if not os.path.exists(src_path):
        raise AssessmentCloneError(
            f"Template DB missing for lab {lab_id}: {src_path}"
        )
    try:
        _copy_file(src_path, dst_path)
        clone.template_db_path = f"lab_{clone.id}_template.db"

        tasks = db.query(LabTask).filter(
            LabTask.lab_id == master.id,
            LabTask.is_deleted == 0,
        ).all()
        for task in tasks:
            db.add(LabTask(
                lab_id=clone.id,
                title=task.title,
                description=task.description,
                correct_answer_hash=task.correct_answer_hash,
                correct_query=task.correct_query,
                order_index=task.order_index,
                created_by=task.created_by,
                is_deleted=0,
                owner_assessment_id=assessment_id,
            ))
        db.flush()
        return clone.id
    except Exception:
        if os.path.exists(dst_path):
            try:
                os.remove(dst_path)
            except OSError:
                pass
        raise


def clone_er_question_for_assessment(db: Session, er_question_id: int, assessment_id: int) -> int:
    """
    Deep-copy a master ER-diagram question into an assessment-owned clone. The stored
    model-answer image is *shared* (same storage key/url) — it is read-only and is never
    physically deleted, so sharing is safe and avoids duplicating blobs.

    Returns the new clone ER-question id. Raises AssessmentCloneError on failure.
    """
    master = db.query(ERDiagramQuestion).filter(
        ERDiagramQuestion.id == er_question_id,
        ERDiagramQuestion.is_deleted == 0,
    ).first()
    if not master:
        raise AssessmentCloneError(f"ER question {er_question_id} not found for cloning")

    clone = ERDiagramQuestion(
        title=master.title,
        problem_statement=master.problem_statement,
        notation=master.notation,
        difficulty_label=master.difficulty_label,
        difficulty_rationale=master.difficulty_rationale,
        rubric_md=master.rubric_md,
        rubric_json=master.rubric_json,
        instruction_history_json=master.instruction_history_json,
        model_answer_storage_key=master.model_answer_storage_key,
        model_answer_url=master.model_answer_url,
        created_by=master.created_by,
        is_deleted=0,
        owner_assessment_id=assessment_id,
    )
    db.add(clone)
    db.flush()
    return clone.id


def clone_item(db: Session, item, assessment_id: int) -> int:
    """
    Dispatch on the polymorphic AssessmentItem.item_type and clone the underlying
    content, returning the new clone's id. Raises AssessmentCloneError for unknown types.
    """
    if item.item_type == "sql_question":
        return clone_question_for_assessment(db, item.item_id, assessment_id)
    if item.item_type in ("sql_lab", "graph_lab"):
        return clone_lab_for_assessment(db, item.item_id, assessment_id)
    if item.item_type == "er_question":
        return clone_er_question_for_assessment(db, item.item_id, assessment_id)
    raise AssessmentCloneError(f"Unknown assessment item_type: {item.item_type}")


def delete_cloned_content(db: Session, assessment_id: int) -> None:
    """
    Tear down all clones owned by an assessment (called on unpublish/delete).

    Physically deletes the heavy SQLite files (question DBs, lab templates + student
    session files) but SOFT-deletes the rows (is_deleted=1) so history endpoints that
    INNER JOIN the content tables still resolve students' past attempts. The shared ER
    model-answer image is never deleted.

    Does not commit; the caller owns the transaction. Note: terminating lab sessions
    commits internally (see terminate_all_lab_sessions), which flushes any pending work.
    """
    # SQL question clones: delete file, soft-delete row.
    q_clones = db.query(Question).filter(
        Question.owner_assessment_id == assessment_id,
        Question.is_deleted == 0,
    ).all()
    for q in q_clones:
        delete_question_database(q.db_file_path)
        q.is_deleted = 1

    # Lab clones: terminate sessions + delete template, soft-delete lab and its tasks.
    lab_clones = db.query(Lab).filter(
        Lab.owner_assessment_id == assessment_id,
        Lab.is_deleted == 0,
    ).all()
    for lab in lab_clones:
        terminate_all_lab_sessions(lab.id, db)
        delete_lab_template(lab.id)
        db.query(LabTask).filter(
            LabTask.lab_id == lab.id,
            LabTask.is_deleted == 0,
        ).update({LabTask.is_deleted: 1}, synchronize_session=False)
        lab.is_deleted = 1

    # ER question clones: soft-delete row only (shared image kept).
    er_clones = db.query(ERDiagramQuestion).filter(
        ERDiagramQuestion.owner_assessment_id == assessment_id,
        ERDiagramQuestion.is_deleted == 0,
    ).all()
    for er in er_clones:
        er.is_deleted = 1

    db.flush()
