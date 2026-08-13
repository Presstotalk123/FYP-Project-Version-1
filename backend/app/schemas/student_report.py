from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.assessment import AssessmentItemComponentScore


class StudentReportSummary(BaseModel):
    """Practice-completion counts for the current student's report page.

    Assessment scores are NOT included here — the frontend reads those from the
    existing GET /student-assessments list (each item already carries its
    weighted_score). This endpoint only aggregates the practice counts that would
    otherwise require an N+1 of per-lab progress calls client-side.
    """
    # Standalone (bank) SQL practice questions the student has completed.
    sql_questions_completed: int
    # Standalone (bank) ER diagram questions the student has passed.
    erd_questions_completed: int
    # Published SQL-type labs where every task has a correct submission.
    sql_labs_completed: int
    # Published graph-type labs where every task has a correct submission.
    graph_labs_completed: int


class StudentReportAssessmentBlock(BaseModel):
    """One submitted assessment in a staff per-student report: the student's own
    weighted score set against the cohort average, plus the per-item breakdown."""
    assessment_id: int
    assessment_title: str
    submitted_at: Optional[datetime] = None
    # This student's weighted total (0-100); None if the assessment is unweighted.
    total_weighted_score: Optional[float] = None
    # Mean weighted total (0-100) across everyone who took the assessment.
    cohort_average: Optional[float] = None
    # True when the student beats the cohort average; None if either score is None.
    above_average: Optional[bool] = None
    # How many students the cohort average is drawn from.
    student_count: int = 0
    # Per-question breakdown (reuses the staff component-scores shape, incl. lab tasks).
    items: List[AssessmentItemComponentScore] = []


class StudentFullReport(BaseModel):
    """Staff-facing consolidated report for one student: practice completion plus a
    per-assessment score breakdown with cohort comparison."""
    student_id: int
    student_email: str
    student_name: Optional[str] = None
    class_group: Optional[str] = None
    summary: StudentReportSummary
    assessments: List[StudentReportAssessmentBlock] = []
