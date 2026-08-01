from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.user import User, UserRole
from app.models.question import Question, Difficulty
from app.schemas.question import (
    QuestionCreate,
    QuestionUpdate,
    QuestionResponse,
    QuestionDetail,
    QuestionListItem
)
from app.dependencies import get_current_user, require_staff_role
from app.utils.db_generator import (
    create_sqlite_from_sql,
    execute_query_on_database,
    delete_question_database,
    SQLValidationError,
    DatabaseGenerationError
)
from app.core.answer_validator import generate_hash
from app.core.advanced_sql_grader import (
    AdvancedGradingError,
    run_advanced_pipeline,
    compute_advanced_hash,
    validate_check_query,
)

router = APIRouter(prefix="/questions", tags=["questions"])

_ADVANCED_STAGE_LABELS = {
    "student": "Reference implementation",
    "test_script": "Test Script",
    "check_query": "Check Query",
    "timeout": "Execution",
}


def _require_answer_rows(results) -> None:
    """Reject model-answer queries that do not produce any rows."""
    if not results:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The correct answer query must return at least one row."
        )


def _require_non_empty(value: Optional[str], label: str) -> None:
    """Reject blank Advanced SQL Testing fields with a clear staff-facing error."""
    if not value or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} is required when Advanced SQL Testing is enabled."
        )


def _advanced_stage_error(exc: AdvancedGradingError) -> HTTPException:
    """Build a staff-facing error naming which pipeline stage failed."""
    label = _ADVANCED_STAGE_LABELS.get(exc.stage, "Advanced SQL Testing")
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{label} failed: {exc.message}"
    )


@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
def create_question(
    question_data: QuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Create a new question (staff only).
    Generates SQLite database from provided SQL statements.

    Args:
        question_data: Question creation data including SQL
        db: Database session
        current_user: Current authenticated staff user

    Returns:
        Created question object

    Raises:
        HTTPException: If SQL validation or database generation fails
    """
    try:
        is_advanced = question_data.advanced_sql_testing

        if is_advanced:
            _require_non_empty(question_data.test_script, "Test Script")
            _require_non_empty(question_data.check_query, "Check Query")
            validate_check_query(question_data.check_query)

        # Generate SQLite database from SQL
        db_filename, db_path = create_sqlite_from_sql(
            question_data.schema_sql,
            question_data.sample_data_sql,
            question_data.correct_answer_query,
            advanced=is_advanced
        )

        if is_advanced:
            # Reference implementation -> Test Script -> Check Query, hash the Check Query's output.
            try:
                columns, results, _ = run_advanced_pipeline(
                    db_path,
                    question_data.correct_answer_query,
                    question_data.test_script,
                    question_data.check_query,
                )
            except AdvancedGradingError as e:
                delete_question_database(db_filename)
                raise _advanced_stage_error(e)
            correct_hash = compute_advanced_hash(columns, results)
        else:
            # Execute the correct answer query to generate hash
            columns, results = execute_query_on_database(
                db_path,
                question_data.correct_answer_query
            )
            try:
                _require_answer_rows(results)
            except HTTPException:
                delete_question_database(db_filename)
                raise

            # Generate hash from correct answer
            correct_hash = generate_hash(results, columns)

        # Create question in database
        new_question = Question(
            title=question_data.title,
            description=question_data.description,
            difficulty=question_data.difficulty,
            schema_sql=question_data.schema_sql,
            sample_data_sql=question_data.sample_data_sql,
            correct_answer_query=question_data.correct_answer_query,
            advanced_sql_testing=1 if is_advanced else 0,
            test_script=question_data.test_script if is_advanced else None,
            check_query=question_data.check_query if is_advanced else None,
            db_file_path=db_filename,
            correct_answer_hash=correct_hash,
            created_by=current_user.id
        )

        db.add(new_question)
        db.commit()
        db.refresh(new_question)

        return new_question

    except HTTPException:
        db.rollback()
        raise
    except SQLValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SQL validation error: {str(e)}"
        )
    except DatabaseGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database generation error: {str(e)}"
        )
    except Exception as e:
        # Rollback on any error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create question: {str(e)}"
        )


@router.get("", response_model=List[QuestionListItem])
def list_questions(
    difficulty: Optional[Difficulty] = Query(None, description="Filter by difficulty"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all questions with optional filters.

    Args:
        difficulty: Filter by difficulty level
        search: Search term for title/description
        skip: Pagination offset
        limit: Maximum results to return
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of questions
    """
    # Exclude assessment-owned clones (owner_assessment_id set) so they never appear in
    # the question bank or the assessment item picker.
    query = db.query(Question).filter(
        Question.is_deleted == 0,
        Question.owner_assessment_id.is_(None),
    )

    # Apply filters
    if difficulty:
        query = query.filter(Question.difficulty == difficulty)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Question.title.ilike(search_term)) |
            (Question.description.ilike(search_term))
        )

    # Order by creation date (newest first) and apply pagination
    questions = query.order_by(Question.created_at.desc()).offset(skip).limit(limit).all()

    return questions


@router.get("/{question_id}", response_model=QuestionDetail)
def get_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific question.

    Args:
        question_id: Question ID
        db: Database session
        current_user: Current authenticated user

    Returns:
        Question details

    Raises:
        HTTPException: If question not found
    """
    question = db.query(Question).filter(
        Question.id == question_id,
        Question.is_deleted == 0
    ).first()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )

    # Students need the database setup, but must never receive the model answer
    # or any trace of Advanced SQL Testing (toggle state, Test Script, Check Query).
    question_detail = QuestionDetail.model_validate(question)
    if current_user.role not in {UserRole.STAFF, UserRole.ADMIN}:
        question_detail.correct_answer_query = None
        question_detail.test_script = None
        question_detail.check_query = None
        question_detail.advanced_sql_testing = False

    return question_detail


@router.put("/{question_id}", response_model=QuestionResponse)
def update_question(
    question_id: int,
    question_data: QuestionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Update a question (staff only).
    If SQL is updated, regenerates the SQLite database.

    Args:
        question_id: Question ID to update
        question_data: Updated question data
        db: Database session
        current_user: Current authenticated staff user

    Returns:
        Updated question object

    Raises:
        HTTPException: If question not found or update fails
    """
    question = db.query(Question).filter(
        Question.id == question_id,
        Question.is_deleted == 0
    ).first()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )

    try:
        # Resolve the advanced-mode flag: explicit value wins, else keep current.
        advanced_sql_testing = (
            question_data.advanced_sql_testing
            if question_data.advanced_sql_testing is not None
            else bool(question.advanced_sql_testing)
        )

        # Check if SQL needs to be regenerated
        sql_changed = (
            question_data.schema_sql is not None or
            question_data.sample_data_sql is not None or
            question_data.correct_answer_query is not None or
            question_data.test_script is not None or
            question_data.check_query is not None or
            question_data.advanced_sql_testing is not None
        )

        if sql_changed:
            # Use existing values if not provided
            schema_sql = question_data.schema_sql if question_data.schema_sql is not None else question.schema_sql
            sample_data_sql = question_data.sample_data_sql if question_data.sample_data_sql is not None else question.sample_data_sql
            correct_answer_query = (
                question_data.correct_answer_query
                if question_data.correct_answer_query is not None
                else question.correct_answer_query
            )
            test_script = (
                question_data.test_script
                if question_data.test_script is not None
                else question.test_script
            )
            check_query = (
                question_data.check_query
                if question_data.check_query is not None
                else question.check_query
            )

            if not correct_answer_query:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A correct answer query is required when regenerating a legacy question."
                )

            if advanced_sql_testing:
                _require_non_empty(test_script, "Test Script")
                _require_non_empty(check_query, "Check Query")
                validate_check_query(check_query)
            else:
                # Toggled off (or staying off): hidden fields no longer apply.
                test_script = None
                check_query = None

            # Generate new SQLite database
            db_filename, db_path = create_sqlite_from_sql(
                schema_sql,
                sample_data_sql,
                correct_answer_query,
                advanced=advanced_sql_testing
            )

            if advanced_sql_testing:
                try:
                    columns, results, _ = run_advanced_pipeline(
                        db_path, correct_answer_query, test_script, check_query
                    )
                except AdvancedGradingError as e:
                    delete_question_database(db_filename)
                    raise _advanced_stage_error(e)
                correct_hash = compute_advanced_hash(columns, results)
            else:
                # Execute correct answer query to generate new hash
                columns, results = execute_query_on_database(db_path, correct_answer_query)
                try:
                    _require_answer_rows(results)
                except HTTPException:
                    delete_question_database(db_filename)
                    raise
                correct_hash = generate_hash(results, columns)

            # Only replace the existing database after the new answer has been validated.
            delete_question_database(question.db_file_path)

            # Update database-related fields
            question.schema_sql = schema_sql
            question.sample_data_sql = sample_data_sql
            question.correct_answer_query = correct_answer_query
            question.test_script = test_script
            question.check_query = check_query
            question.advanced_sql_testing = 1 if advanced_sql_testing else 0
            question.db_file_path = db_filename
            question.correct_answer_hash = correct_hash

        # Update other fields if provided
        if question_data.title is not None:
            question.title = question_data.title
        if question_data.description is not None:
            question.description = question_data.description
        if question_data.difficulty is not None:
            question.difficulty = question_data.difficulty

        db.commit()
        db.refresh(question)

        return question

    except SQLValidationError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SQL validation error: {str(e)}"
        )
    except DatabaseGenerationError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database generation error: {str(e)}"
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update question: {str(e)}"
        )


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Soft delete a question (staff only).
    Also deletes the associated SQLite database file.

    Args:
        question_id: Question ID to delete
        db: Database session
        current_user: Current authenticated staff user

    Raises:
        HTTPException: If question not found
    """
    question = db.query(Question).filter(
        Question.id == question_id,
        Question.is_deleted == 0
    ).first()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )

    # Soft delete
    question.is_deleted = 1

    # Delete the SQLite database file
    delete_question_database(question.db_file_path)

    db.commit()

    return None
