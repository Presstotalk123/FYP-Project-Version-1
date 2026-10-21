from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.cache import Ns, cache_read
from app.database import get_db
from app.dependencies import get_current_user
from app.models.lab import Lab
from app.models.user import User, UserRole
from app.schemas.leaderboard import LabLeaderboardResponse, OverallLeaderboardResponse
from app.services import leaderboard as leaderboard_service

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/labs/{lab_id}", response_model=LabLeaderboardResponse)
def get_lab_leaderboard(
    lab_id: int,
    class_group: Optional[str] = Query(None, description="Filter to one class group; omit for all"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rank the students who have submitted to one practice lab.

    Students only see published labs, and get ``correctness_hidden`` (no rows) for a
    lab whose results are hidden — the leaderboard would otherwise reveal correctness.
    Both checks read the Lab row live, outside the cache, so a publish/hide toggle
    takes effect immediately.
    """
    lab = (
        db.query(Lab.id, Lab.title, Lab.lab_type, Lab.is_published, Lab.hide_correctness)
        .filter(Lab.id == lab_id, Lab.is_deleted == 0, Lab.owner_assessment_id.is_(None))
        .first()
    )
    is_student = current_user.role == UserRole.STUDENT
    if lab is None or (is_student and lab.is_published != 1):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab not found")

    if is_student and lab.hide_correctness == 1:
        return LabLeaderboardResponse(
            lab_id=lab.id,
            title=lab.title,
            lab_type=lab.lab_type,
            tasks=[],
            rows=[],
            class_groups=[],
            correctness_hidden=True,
        )

    # Shares the LAB_ANALYTICS namespace, which is auto-invalidated whenever a lab
    # submission or user changes (see app/core/cache.py). The cached payload is
    # unmasked; apply_viewer tailors it per request.
    payload = cache_read(
        db,
        Ns.LAB_ANALYTICS,
        key=("leaderboard", lab_id, class_group or ""),
        producer=lambda: leaderboard_service.lab_leaderboard(db, lab_id, class_group),
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab not found")
    return leaderboard_service.apply_viewer(payload, current_user)


@router.get("/overall", response_model=OverallLeaderboardResponse)
def get_overall_leaderboard(
    class_group: Optional[str] = Query(None, description="Filter to one class group; omit for all"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rank every active student by SQL questions + ER questions + labs completed."""
    payload = leaderboard_service.overall_leaderboard(db, class_group)
    return leaderboard_service.apply_viewer(payload, current_user)
