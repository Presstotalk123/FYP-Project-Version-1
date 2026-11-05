"""Disposable real Akela backend for normalization browser tests; never deployed."""
import os
from pathlib import Path
import sys
import tempfile

scratch = tempfile.TemporaryDirectory(prefix="akela-normalization-browser-")
os.environ.update(DATABASE_URL="sqlite:///" + str(Path(scratch.name) / "app.db"),
                  SECRET_KEY="normalization-browser-tests-only", RA_ENABLED="false",
                  QUESTION_DB_PATH=str(Path(scratch.name) / "questions") + os.sep,
                  LAB_DB_PATH=str(Path(scratch.name) / "labs") + os.sep,
                  CORS_ORIGINS='["http://127.0.0.1:3019"]',
                  NORMALIZATION_SEMANTIC_API_KEY="", NORMALIZATION_SEMANTIC_MODEL="")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.main import app
from app.database import SessionLocal
from app.models.user import User, UserRole
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.normalization import NormalizationQuestion
from app.core.security import create_access_token
from app.services.normalization.assessment import clone_for_assessment

with SessionLocal() as db:
    db.add_all([User(id=1, email="staff@normalization.example.com", hashed_password="", role=UserRole.STAFF),
                User(id=2, email="student@normalization.example.com", hashed_password="", role=UserRole.STUDENT, class_group="G1")])
    db.flush()
    for identifier, title, attrs, fds in (
        (1, "Normalization browser exercise", ["A", "B"], [{"lhs": ["A"], "rhs": ["B"]}]),
        (2, "Canvas browser exercise", ["A", "B", "C"], [{"lhs": ["A"], "rhs": ["B"]}, {"lhs": ["C"], "rhs": ["A"]}]),
    ):
        db.add(NormalizationQuestion(id=identifier, title=title, difficulty="easy", scenario="Construct the dependencies and normalize the relation.",
            relation_name="R", attributes=attrs, statements=[{"id": "S1", "text": "Each A identifies one B."},
                *([{"id": "S2", "text": "Each C identifies one A."}] if identifier == 2 else [])], sample_rows=[],
            target_normal_form="BCNF", approved_fds=fds, created_by=1, approved_by=1, is_published=1))
    db.add(Assessment(id=1, title="Hidden normalization assessment", is_published=1, is_running=1, created_by=1))
    db.flush()
    clone_id = clone_for_assessment(db, 1, 1, hide_correctness=1)
    db.add(AssessmentItem(id=1, assessment_id=1, item_type="normalization_question", item_id=clone_id, weight=100, hide_correctness=1))
    db.commit()


@app.get("/test-token/{role}")
def token(role: str):
    return {"token": create_access_token({"sub": f"{'staff' if role == 'staff' else 'student'}@normalization.example.com"}),
            "clone_id": clone_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8019, log_level="warning")
