"""Staff-only research/LAD export endpoints.

- GET /admin/export/summary   — cohort-level JSON aggregate, cached daily (date-stamped key).
- GET /admin/export/raw-csv   — streamed per-student anonymized CSV.

Both are protected by require_staff_role. Not gated behind AKELA_AGENTS_ENABLED: with the
flag off, the Akela-specific sections simply degrade to empty/zero while system scale and
misconception taxonomy stay meaningful.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import Ns, cache_read
from app.database import get_db
from app.dependencies import require_staff_role
from app.models.user import User
from app.schemas.research_export import ResearchExportSummary
from app.services import research_export

router = APIRouter(prefix="/admin/export", tags=["research-export"])


@router.get("/summary", response_model=ResearchExportSummary)
def get_export_summary(
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    # Heavy multi-query aggregate: read with a date-stamped key so it refreshes once a day
    # (the RESEARCH_EXPORT namespace has no after_flush invalidation hook, by design).
    return cache_read(
        db,
        Ns.RESEARCH_EXPORT,
        key=("summary", date.today().isoformat()),
        producer=lambda: research_export.compute_summary(db),
    )


@router.get("/raw-csv")
def get_raw_csv_export(
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    # Fail closed: refuse rather than emit a weakly-anonymized (empty-key HMAC) export.
    if not settings.RESEARCH_EXPORT_SALT:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RESEARCH_EXPORT_SALT is not configured",
        )
    return StreamingResponse(
        research_export.stream_raw_csv_rows(db),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=research_export.csv"},
    )
