from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session


@dataclass
class ItemView:
    kind: str
    ref_id: Optional[int]
    title: str
    difficulty: Optional[str] = None
    detail: dict = field(default_factory=dict)


@dataclass
class GradeResult:
    is_passed: bool
    score_earned: Optional[float] = None
    score_total: Optional[float] = None
    detail: dict = field(default_factory=dict)
    message: str = ""


class LabItemHandler(ABC):
    """One implementation per lab_item `kind`. erd grading is streamed separately (see erd_handler)."""
    kind: str

    @abstractmethod
    def resolve(self, db: Session, ref_id: Optional[int]) -> Any:
        """Return the referenced domain object (or raise 404-shaped ValueError)."""

    @abstractmethod
    def to_view(self, db: Session, ref_id: Optional[int]) -> ItemView:
        """Student/staff-facing summary for the item list."""

    def grade(self, db: Session, ref_id: Optional[int], payload: dict, session: Any) -> GradeResult:
        """Synchronous grade. erd overrides with a streaming path instead (raises here)."""
        raise NotImplementedError(f"{self.kind} grading is not synchronous")
