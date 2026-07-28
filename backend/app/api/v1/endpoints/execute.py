from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models.user import User
from app.models.question import Question
from app.models.attempt import Attempt
from app.models.progress import UserProgress
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

router = APIRouter(prefix="/execute", tags=["execute"])

# Shown to students when the hidden Test Script or Check Query stage fails —
# never the raw SQLite error, which could leak hidden table/column names.
_ADVANCED_GENERIC_ERROR = (
    "Your submission could not be verified. Please check your SQL and try again."
)


def _grade_advanced_submission(db_path: str, query: str, question: Question):
    """
    Grade a student's submission for an Advanced SQL Testing question: apply
    the submission, run the hidden Test Script, run the hidden Check Query,
    and compare its hash to the stored reference hash.

    Returns:
        Tuple of (is_correct, error_message, execution_time_ms). Never
        includes the Check Query's raw output, and never surfaces a raw
        error from the hidden Test Script/Check Query stages to the student.
    """
    try:
        is_permissive_but_safe(query, "student")
        columns, results, execution_time_ms = run_advanced_pipeline(
            db_path, query, question.test_script, question.check_query
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

    is_correct = compute_advanced_hash(columns, results) == question.correct_answer_hash
    return is_correct, None, execution_time_ms


@router.post("", response_model=ExecuteResponse)
def execute_query(
    execute_request: ExecuteRequest,
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

    # Get the database file path
    db_path = get_question_db_path(question.db_file_path)

    if question.advanced_sql_testing:
        is_correct, error_message, execution_time_ms = _grade_advanced_submission(
            db_path, execute_request.query, question
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
                question.correct_answer_hash
            )
        else:
            # Query failed, so it's definitely not correct
            is_correct = False

    # Log the attempt
    attempt = Attempt(
        user_id=current_user.id,
        question_id=execute_request.question_id,
        query=execute_request.query,
        is_correct=1 if is_correct else 0,
        execution_time_ms=result["execution_time_ms"],
        error_message=error_message
    )
    db.add(attempt)

    # Update or create user progress
    progress = db.query(UserProgress).filter(
        UserProgress.user_id == current_user.id,
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
            user_id=current_user.id,
            question_id=execute_request.question_id,
            completed=1 if is_correct else 0,
            attempts_count=1,
            last_attempted_at=datetime.utcnow(),
            first_completed_at=datetime.utcnow() if is_correct else None
        )
        db.add(progress)

    # Clean up old attempts - keep only 4 most recent
    old_attempts = (
        db.query(Attempt)
        .filter(
            Attempt.user_id == current_user.id,
            Attempt.question_id == execute_request.question_id
        )
        .order_by(Attempt.submitted_at.desc())
        .offset(4)  # Skip the 4 most recent
        .all()
    )

    for old_attempt in old_attempts:
        db.delete(old_attempt)

    db.commit()

    # Return the response
    return ExecuteResponse(
        is_correct=is_correct,
        execution_time_ms=result["execution_time_ms"],
        results=result["results"],
        columns=result["columns"],
        error_message=error_message,
        row_count=result["row_count"]
    )
