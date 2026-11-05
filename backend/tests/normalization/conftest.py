"""Isolated API fixtures: no developer DB, credentials, or live AI calls."""
import os
import atexit
import tempfile
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("SECRET_KEY", "normalization-tests-only")
# Other existing API suites import app.main during collection. Configure the shared
# application before importing any app module so collection never opens a real DB.
_scratch = tempfile.TemporaryDirectory(prefix="akela-normalization-suite-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_scratch.name) / "suite.db")
os.environ["QUESTION_DB_PATH"] = str(Path(_scratch.name) / "questions") + os.sep
os.environ["LAB_DB_PATH"] = str(Path(_scratch.name) / "labs") + os.sep
os.environ["RA_ENABLED"] = "false"

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from app.database import Base, get_db, engine as application_engine
from app.models.user import User, UserRole
from app.api.v1.endpoints import normalization, assessments, student_assessments, questions, execute, er_diagram, labs
from app.config import settings
from app.core.security import create_access_token
from app.core import cache as read_cache

atexit.register(application_engine.dispose)


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(read_cache, "_store", {})
    postgres = os.environ.get("NORMALIZATION_TEST_POSTGRES_URL")
    schema = None
    if postgres:
        url = make_url(postgres)
        if url.host != "127.0.0.1" or url.port != 55439 or url.username != "normalization_test":
            raise RuntimeError("PostgreSQL tests require the disposable normalization test server on port 55439")
        schema = "normalization_test_" + uuid4().hex
        engine = create_engine(postgres, connect_args={"options": f"-csearch_path={schema}"})
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    for module in (normalization, assessments, student_assessments, questions, execute, er_diagram, labs):
        app.include_router(module.router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    def database():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(settings, "NORMALIZATION_SEMANTIC_API_KEY", "")
    monkeypatch.setattr(settings, "NORMALIZATION_SEMANTIC_MODEL", "")
    monkeypatch.setattr(settings, "QUESTION_DB_PATH", str(tmp_path / "questions") + os.sep)
    monkeypatch.setattr(settings, "LAB_DB_PATH", str(tmp_path / "labs") + os.sep)
    headers = {}
    with sessions() as db:
        for name, role in (("student", UserRole.STUDENT), ("other", UserRole.STUDENT),
                           ("staff", UserRole.STAFF), ("admin", UserRole.ADMIN)):
            user = User(email=f"{name}@normalization.test", hashed_password="unused", role=role, is_active=1)
            db.add(user)
            db.flush()
            headers[name] = {"Authorization": f"Bearer {create_access_token({'sub': user.email, 'role': role.value})}"}
        db.commit()
    with TestClient(app) as client:
        yield client, headers, sessions
    if schema:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
    engine.dispose()
