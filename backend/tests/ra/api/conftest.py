"""Fixtures for the RA API tests.

Every path the app writes to is redirected into a temp directory and the RA flags are
reset to their defaults *before* the app is imported, so the tests never touch a
developer's real data and never depend on their local backend/.env.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="akela_ra_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'app.db')}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["LAB_DB_PATH"] = os.path.join(_TMP, "lab_databases") + os.sep
os.environ["QUESTION_DB_PATH"] = os.path.join(_TMP, "question_databases") + os.sep
os.environ["RA_ENABLED"] = "false"
os.environ["RA_AGGREGATE_NULLS"] = "sql"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.config import settings  # noqa: E402


def _headers(email: str, role: UserRole) -> dict:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, hashed_password=hash_password("pw"), role=role))
            db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {create_access_token({'sub': email, 'role': role.value})}"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def student_headers(client):
    return _headers("student@test.example.com", UserRole.STUDENT)


@pytest.fixture(scope="session")
def staff_headers(client):
    return _headers("staff@test.example.com", UserRole.STAFF)


@pytest.fixture
def ra_on(monkeypatch):
    monkeypatch.setattr(settings, "RA_ENABLED", True)
