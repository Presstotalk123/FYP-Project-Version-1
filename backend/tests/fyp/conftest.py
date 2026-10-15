"""Shared fixtures for the FYP test suite.

Every path the app writes to (application DB, question and lab database folders) is
redirected into a per-session temp directory *before* the app is imported, so the
suite never touches a developer's real data.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="akela_fyp_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'app.db')}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["LAB_DB_PATH"] = os.path.join(_TMP, "lab_databases") + os.sep
os.environ["QUESTION_DB_PATH"] = os.path.join(_TMP, "question_databases") + os.sep

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.user import User, UserRole
from app.core.security import create_access_token, hash_password


def _ensure_user(email: str, role: UserRole) -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, hashed_password=hash_password("pw"), role=role))
            db.commit()
    finally:
        db.close()


def _headers(email: str, role: UserRole) -> dict:
    _ensure_user(email, role)
    token = create_access_token({"sub": email, "role": role.value})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def staff_headers(client):
    return _headers("staff@test.local", UserRole.STAFF)


@pytest.fixture(scope="session")
def student_headers(client):
    return _headers("student@test.local", UserRole.STUDENT)
