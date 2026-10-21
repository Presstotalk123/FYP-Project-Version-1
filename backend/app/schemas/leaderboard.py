import datetime as _dt
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class LabLeaderboardTask(BaseModel):
    """One column of the per-lab leaderboard, in the lab's task order."""
    task_id: int
    title: str
    order_index: int


class LabLeaderboardRow(BaseModel):
    """One student's standing in a lab.

    For student viewers, ``student_id`` and ``email`` are always null and other
    students' ``display_name`` is masked; only the viewer's own row (``is_me``) is not.
    """
    rank: int = Field(..., description="Competition rank (1, 1, 3) by tasks solved, then finished_at")
    student_id: Optional[int] = Field(None, description="Null for student viewers")
    display_name: str
    email: Optional[str] = Field(None, description="Null for student viewers")
    class_group: Optional[str] = None
    tasks_correct: int = Field(..., description="Distinct tasks with at least one correct submission")
    total_tasks: int
    task_status: List[Literal["solved", "attempted", "not_attempted"]] = Field(
        ..., description="Per task, in the same order as the response's tasks"
    )
    submissions: int = Field(..., description="Total task submissions to this lab")
    finished_at: Optional[_dt.datetime] = Field(
        None, description="When the student reached their current score (latest first-correct submission)"
    )
    completed: bool = Field(..., description="Every task solved")
    is_me: bool = False


class LabLeaderboardResponse(BaseModel):
    lab_id: int
    title: str
    lab_type: str
    tasks: List[LabLeaderboardTask]
    rows: List[LabLeaderboardRow]
    class_groups: List[str] = Field(..., description="Class groups available to filter by")
    my_rank: Optional[int] = Field(None, description="The student viewer's rank, if they are listed")
    correctness_hidden: bool = Field(
        False, description="True when the lab hides correctness from students; rows is then empty"
    )


class OverallLeaderboardRow(BaseModel):
    """One student's practice completions across SQL questions, ER questions and labs."""
    rank: int = Field(..., description="Competition rank (1, 1, 3) by total")
    student_id: Optional[int] = Field(None, description="Null for student viewers")
    display_name: str
    email: Optional[str] = Field(None, description="Null for student viewers")
    class_group: Optional[str] = None
    sql_completed: int
    erd_completed: int
    labs_completed: int
    total: int
    is_me: bool = False


class OverallLeaderboardResponse(BaseModel):
    rows: List[OverallLeaderboardRow]
    class_groups: List[str]
    my_rank: Optional[int] = None
