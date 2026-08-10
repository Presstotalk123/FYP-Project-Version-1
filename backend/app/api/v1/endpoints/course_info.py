"""Student-facing course syllabus (Markdown), editable by staff/admin.

Single stored record (CourseInfo, id==1) — no version history. Students read the
rendered Markdown on the Course Info page; staff edit it from the Settings page.
When no row exists yet, GET falls back to DEFAULT_COURSE_INFO_MD so the page is
never empty before the first save. The read is served from the in-process cache
(Ns.COURSE_INFO), invalidated by a version bump on each save.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.core.cache import cache_read, bump_version, Ns
from app.models.course_info import CourseInfo
from app.models.user import User
from app.schemas.course_info import CourseInfoResponse, CourseInfoUpdate
from app.services.course_info_default import DEFAULT_COURSE_INFO_MD

router = APIRouter(prefix="/course-info", tags=["course-info"])

SINGLETON_ID = 1


@router.get("", response_model=CourseInfoResponse)
def get_course_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the course syllabus Markdown (seeded default until first edited).

    The content is cached in-process under Ns.COURSE_INFO — identical for every
    reader and recomputed only after a staff save bumps the version.
    """
    row = db.query(CourseInfo).filter(CourseInfo.id == SINGLETON_ID).first()

    def producer() -> str:
        return row.content if row else DEFAULT_COURSE_INFO_MD

    content = cache_read(db, Ns.COURSE_INFO, key=("content",), producer=producer)

    return CourseInfoResponse(content=content)


@router.put("", response_model=CourseInfoResponse)
def update_course_info(
    payload: CourseInfoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Overwrite the single course-info record (staff/admin only)."""
    row = db.query(CourseInfo).filter(CourseInfo.id == SINGLETON_ID).first()
    if row is None:
        row = CourseInfo(id=SINGLETON_ID, content=payload.content)
        db.add(row)
    else:
        row.content = payload.content

    # Bump before commit so the cached copy invalidates atomically with the write.
    bump_version(db, Ns.COURSE_INFO)
    db.commit()
    db.refresh(row)

    return CourseInfoResponse(content=row.content)
