from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.database import get_db
from app.models.user import User
from app.models.question import Question
from app.models.attempt import Attempt
from app.models.progress import UserProgress
from app.models.assessment_item import AssessmentItem
from app.schemas.attempt import ExecuteRequest, ExecuteResponse
from app.dependencies import get_current_user
from app.core.query_executor import execute_student_query
from app.core.answer_validator import validate_answer
from app.utils.db_generator import get_question_db_path
from app.core.advanced_sql_grader import (
    AdvancedGradingError,
    is_permissive_but_safe,
    run_advanced_pipeline,
    compute_advanced_hash,
)
from app.services.assessment_timer import (
    get_active_assessment_session,
    enforce_not_expired,
    credit_query_time,
)

router = APIRouter(prefix="/execute", tags=["execute"])

# Shown to students when the hidden Test Script or Check Query stage fails —
# never the raw SQLite error, which could leak hidden table/column names.
_ADVANCED_GENERIC_ERROR = (
    "Your submission could not be verified. Please check your SQL and try again."
)


def _grade_advanced_submission(
    db_path: str,
    query: str,
    test_script: str,
    check_query: str,
    correct_answer_hash: str,
):
    """
    Grade a student's submission for an Advanced SQL Testing question: apply
    the submission, run the hidden Test Script, run the hidden Check Query,
    and compare its hash to the stored reference hash.

    Takes the question's grading fields as plain values (not the ORM object) so
    it can run *after* the request has released its Postgres connection back to
    the pool — the multi-second SQLite pipeline must not pin a DB connection.

    Returns:
        Tuple of (is_correct, error_message, execution_time_ms). Never
        includes the Check Query's raw output, and never surfaces a raw
        error from the hidden Test Script/Check Query stages to the student.
    """
    try:
        is_permissive_but_safe(query, "student")
        columns, results, execution_time_ms = run_advanced_pipeline(
            db_path, query, test_script, check_query
        )
    except AdvancedGradingError as e:
        execution_time_ms = 0.0
        if e.stage in ("student", "timeout"):
            # The student's own submission (or a generic timeout message that
            # never contains hidden-script content) is safe to show verbatim.
            return False, e.message, execution_time_ms
        # Hidden Test Script/Check Query failures must never leak their
        # underlying error text (could reveal hidden table/column names).
        return False, _ADVANCED_GENERIC_ERROR, execution_time_ms

    is_correct = compute_advanced_hash(columns, results) == correct_answer_hash
    return is_correct, None, execution_time_ms


@router.post("", response_model=ExecuteResponse)
def execute_query(
    execute_request: ExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute a SQL query against a question's database and validate the answer.

    Args:
        execute_request: Query execution request
        db: Database session
        current_user: Current authenticated user

    Returns:
        Execution results with validation

    Raises:
        HTTPException: If question not found or execution fails
    """
    # Capture the caller's identity up front. After the read phase commits below,
    # the ORM expires attributes on `current_user`/`question`, so we read everything
    # we need into plain locals now to avoid triggering surprise reload queries
    # (each of which would re-check-out a scarce Postgres connection).
    user_id = current_user.id
    user_role = current_user.role.value

    # --- READ PHASE (short Postgres transaction) ---
    # Get the question
    question = db.query(Question).filter(
        Question.id == execute_request.question_id,
        Question.is_deleted == 0
    ).first()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )

    # Snapshot the fields needed after the connection is released.
    q_owner_assessment_id = question.owner_assessment_id
    q_advanced = question.advanced_sql_testing
    q_test_script = question.test_script
    q_check_query = question.check_query
    q_correct_hash = question.correct_answer_hash
    q_hide_correctness = bool(question.hide_correctness)
    db_path = get_question_db_path(question.db_file_path)

    # Assessment timer: cloned assessment content carries owner_assessment_id. When set,
    # enforce lazy expiration before running and credit the query time afterwards so the
    # student doesn't lose assessment time while the query executes.
    assessment_session = None
    query_start = None
    if q_owner_assessment_id:
        assessment_session = get_active_assessment_session(
            db, q_owner_assessment_id, user_id
        )
        if assessment_session is None:
            # Session already submitted/expired — the assessment is over for this student.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Assessment has ended.",
            )
        enforce_not_expired(db, assessment_session)  # 403 + finalize if past end_time
        # Start crediting from when the request entered the app (set by the received_at
        # middleware), so time spent waiting for a threadpool worker under load is credited
        # too — not just the handler's own execution time.
        query_start = getattr(request.state, "received_at", None) or datetime.now(timezone.utc)

    # Per-question max-queries cap: only for students on assessment content. Look up the
    # matching AssessmentItem override (item_id points at this clone question after publish)
    # and, if a limit is set, block once the student has already used it up. The check runs
    # before the attempts_count increment below, so the Nth run is allowed and the (N+1)th
    # is rejected. Staff/preview are never capped.
    q_max_queries = None
    if q_owner_assessment_id and user_role == "student":
        item = db.query(AssessmentItem.max_queries).filter(
            AssessmentItem.assessment_id == q_owner_assessment_id,
            AssessmentItem.item_type == "sql_question",
            AssessmentItem.item_id == execute_request.question_id,
        ).first()
        q_max_queries = item[0] if item else None
        if q_max_queries is not None:
            used = db.query(UserProgress.attempts_count).filter(
                UserProgress.user_id == user_id,
                UserProgress.question_id == execute_request.question_id,
            ).scalar() or 0
            if used >= q_max_queries:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You have reached the maximum number of queries allowed for this question.",
                )

    # Release the Postgres connection back to the pool before running the untrusted
    # SQLite query. That query can take up to 5–15s; holding a connection (and, behind
    # PgBouncer, a real server backend) for its whole duration is what exhausts the
    # base-tier connection budget under load. Committing here ends the read transaction
    # so the connection is freed; the write phase re-checks one out for a few ms.
    db.commit()

    # --- QUERY PHASE (no Postgres transaction held) ---
    # Execution + persistence run inside try/finally so the query time is credited back even
    # if something raises (e.g. a timeout under load) — the spec credits Error responses too.
    try:
        if q_advanced:
            is_correct, error_message, execution_time_ms = _grade_advanced_submission(
                db_path, execute_request.query,
                q_test_script, q_check_query, q_correct_hash,
            )
            result = {
                "columns": [],
                "results": [],
                "row_count": 0,
                "execution_time_ms": execution_time_ms,
            }
        else:
            # Execute the query
            result = execute_student_query(db_path, execute_request.query)

            # Initialize validation result
            is_correct = False
            error_message = result.get("error_message")

            # If execution was successful, validate the answer
            if result["success"]:
                is_correct = validate_answer(
                    result["raw_results"],
                    result["columns"],
                    q_correct_hash
                )
            else:
                # Query failed, so it's definitely not correct
                is_correct = False

        # --- WRITE PHASE (short Postgres transaction) ---
        # Log the attempt
        attempt = Attempt(
            user_id=user_id,
            question_id=execute_request.question_id,
            query=execute_request.query,
            is_correct=1 if is_correct else 0,
            execution_time_ms=result["execution_time_ms"],
            error_message=error_message
        )
        db.add(attempt)

        # Update or create user progress
        progress = db.query(UserProgress).filter(
            UserProgress.user_id == user_id,
            UserProgress.question_id == execute_request.question_id
        ).first()

        if progress:
            # Update existing progress
            progress.attempts_count += 1
            progress.last_attempted_at = datetime.utcnow()

            # If this is the first correct answer, mark as completed
            if is_correct and not progress.completed:
                progress.completed = 1
                progress.first_completed_at = datetime.utcnow()
        else:
            # Create new progress record
            progress = UserProgress(
                user_id=user_id,
                question_id=execute_request.question_id,
                completed=1 if is_correct else 0,
                attempts_count=1,
                last_attempted_at=datetime.utcnow(),
                first_completed_at=datetime.utcnow() if is_correct else None
            )
            db.add(progress)

        # Capture the post-increment count into a plain local now — after the commit below the
        # ORM expires attributes and reading progress.attempts_count would trigger a reload.
        attempts_used = progress.attempts_count

        # Full attempt history is retained (previously pruned to the 4 most recent) so staff
        # analytics can show a student's complete query history and count queries-to-correct.

        db.commit()
    finally:
        # Credit the query execution time back to the assessment deadline (no-op if untimed).
        if query_start is not None:
            credit_query_time(db, assessment_session, query_start)

    # Real correctness is always persisted above (Attempt/UserProgress) for grading, but
    # questions with hide_correctness on don't reveal it to students in the response — they
    # get is_correct=None and the frontend shows a neutral "Submitted" state.
    student_hidden = q_hide_correctness and user_role == "student"

    # Return the response, carrying the freshly-credited deadline so the frontend can resume
    # its countdown without a separate session round-trip.
    return ExecuteResponse(
        is_correct=None if student_hidden else is_correct,
        execution_time_ms=result["execution_time_ms"],
        results=result["results"],
        columns=result["columns"],
        error_message=error_message,
        row_count=result["row_count"],
        assessment_end_time=assessment_session.end_time if assessment_session else None,
        max_queries=q_max_queries,
        attempts_used=attempts_used if q_max_queries is not None else None,
    )
