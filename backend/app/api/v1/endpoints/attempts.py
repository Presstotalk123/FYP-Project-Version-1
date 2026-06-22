from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.user import User
from app.models.attempt import Attempt
from app.models.question import Question
from app.models.progress import UserProgress
from app.schemas.attempt import AttemptResponse, AttemptHistory, ProgressResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/attempts", tags=["attempts"])


@router.get("", response_model=List[AttemptResponse])
def get_user_attempts(
    question_id: Optional[int] = Query(None, description="Filter by question ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of attempts to return"),
    skip: int = Query(0, ge=0, description="Number of attempts to skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's attempt history.

    Args:
        question_id: Optional filter by specific question
        limit: Maximum results to return
        skip: Pagination offset
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of attempts
    """
    query = db.query(Attempt).filter(Attempt.user_id == current_user.id)

    # Filter by question if specified
    if question_id is not None:
        query = query.filter(Attempt.question_id == question_id)

    # Order by most recent first and apply pagination
    attempts = query.order_by(Attempt.submitted_at.desc()).offset(skip).limit(limit).all()

    return attempts


@router.get("/history", response_model=List[AttemptHistory])
def get_attempt_history_with_details(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of attempts to return"),
    skip: int = Query(0, ge=0, description="Number of attempts to skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's attempt history with question details.

    Args:
        limit: Maximum results to return
        skip: Pagination offset
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of attempts with question information
    """
    # Join attempts with questions to get question titles
    attempts_with_questions = (
        db.query(
            Attempt.id,
            Attempt.question_id,
            Question.title.label("question_title"),
            Attempt.query,
            Attempt.is_correct,
            Attempt.execution_time_ms,
            Attempt.submitted_at
        )
        .join(Question, Attempt.question_id == Question.id)
        .filter(Attempt.user_id == current_user.id)
        .order_by(Attempt.submitted_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Convert to response format
    result = []
    for attempt in attempts_with_questions:
        result.append(AttemptHistory(
            id=attempt.id,
            question_id=attempt.question_id,
            question_title=attempt.question_title,
            query=attempt.query,
            is_correct=bool(attempt.is_correct),
            execution_time_ms=attempt.execution_time_ms,
            submitted_at=attempt.submitted_at
        ))

    return result


@router.get("/progress", response_model=List[ProgressResponse])
def get_user_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's progress on all attempted questions.

    Args:
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of progress records with question information
    """
    # Join progress with questions
    progress_with_questions = (
        db.query(
            UserProgress.question_id,
            Question.title.label("question_title"),
            UserProgress.completed,
            UserProgress.attempts_count,
            UserProgress.last_attempted_at,
            UserProgress.first_completed_at
        )
        .join(Question, UserProgress.question_id == Question.id)
        .filter(UserProgress.user_id == current_user.id)
        .order_by(UserProgress.last_attempted_at.desc())
        .all()
    )

    # Convert to response format
    result = []
    for progress in progress_with_questions:
        result.append(ProgressResponse(
            question_id=progress.question_id,
            question_title=progress.question_title,
            completed=bool(progress.completed),
            attempts_count=progress.attempts_count,
            last_attempted_at=progress.last_attempted_at,
            first_completed_at=progress.first_completed_at
        ))

    return result


@router.get("/question/{question_id}", response_model=List[AttemptResponse])
def get_question_attempts(
    question_id: int,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of attempts to return"),
    skip: int = Query(0, ge=0, description="Number of attempts to skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's attempts for a specific question.

    Args:
        question_id: Question ID
        limit: Maximum results to return
        skip: Pagination offset
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of attempts for the question

    Raises:
        HTTPException: If question not found
    """
    # Verify question exists
    question = db.query(Question).filter(
        Question.id == question_id,
        Question.is_deleted == 0
    ).first()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )

    # Get attempts
    attempts = (
        db.query(Attempt)
        .filter(
            Attempt.user_id == current_user.id,
            Attempt.question_id == question_id
        )
        .order_by(Attempt.submitted_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return attempts
