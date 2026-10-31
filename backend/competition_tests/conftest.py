import os
from pathlib import Path
import sys
import uuid

os.environ.setdefault("SECRET_KEY", "rescue-tests-only-not-a-production-key")
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.api.v1.endpoints.competitions import router


def document(prefix="Demo", difficulty="easy"):
    people, addresses = prefix + "People", prefix + "Addresses"
    reference = f'SELECT p.name AS name, a.city AS city FROM {people} p LEFT JOIN {addresses} a ON a.person_id=p.id'
    count = f'SELECT COUNT(*) AS records FROM {people}'
    return {
        "title": prefix + " directory incident", "topic": "joins", "difficulty": difficulty,
        "complaint": "A person without an address disappeared from the application directory.",
        "business_rules": "Show every person with their matching address, preserving unmatched people with NULL city values.",
        "schema_sql": f'CREATE TABLE {people}(id INTEGER, name TEXT); CREATE TABLE {addresses}(id INTEGER, person_id INTEGER, city TEXT);',
        "components": [
            {"id": "directory", "label": "Directory", "purpose": "Displays people and locations.", "query": reference.replace("LEFT JOIN", "INNER JOIN"), "reference_query": reference},
            {"id": "summary", "label": "Record summary", "purpose": "Counts registered people.", "query": count, "reference_query": count},
        ],
        "culprit_component": "directory", "fault_template": "left_to_inner:v1",
        "fault_cause": "The inner join drops unmatched people, but the directory must preserve those records.",
        "checkpoints": ["Compare people with the directory.", "Inspect unmatched rows in the join."],
        "scenarios": [
            {"id": "visible", "label": "Unmatched person", "visible": True, "seed_sql": f"INSERT INTO {people} VALUES (1,'A'),(2,'B'); INSERT INTO {addresses} VALUES (10,2,'East');", "approved_outputs": {"directory": {"columns": ["name", "city"], "rows": [["A", None], ["B", "East"]]}, "summary": {"columns": ["records"], "rows": [[2]]}}},
            {"id": "matched", "label": "All matched", "visible": False, "seed_sql": f"INSERT INTO {people} VALUES (3,'C'); INSERT INTO {addresses} VALUES (11,3,'West');", "approved_outputs": {"directory": {"columns": ["name", "city"], "rows": [["C", "West"]]}, "summary": {"columns": ["records"], "rows": [[1]]}}},
            {"id": "empty", "label": "No people", "visible": False, "seed_sql": "", "approved_outputs": {"directory": {"columns": ["name", "city"], "rows": []}, "summary": {"columns": ["records"], "rows": [[0]]}}},
        ], "oracle_confirmed": True, "alternative_repairs": [reference],
    }


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "COMPETITIONS_ENABLED", True)
    monkeypatch.setattr(settings, "COMPETITION_DB_PATH", str(tmp_path / "fixtures"))
    monkeypatch.setattr(settings, "RESEARCH_EXPORT_SALT", "test-salt")
    postgres_url = os.environ.get("COMPETITION_TEST_DATABASE_URL")
    cleanup_engine, schema = None, None
    if postgres_url:
        if not (make_url(postgres_url).database or "").endswith("_test"):
            raise RuntimeError("PostgreSQL integration tests require a database named *_test")
        schema = "rescue_test_" + uuid.uuid4().hex
        cleanup_engine = create_engine(postgres_url)
        with cleanup_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = create_engine(postgres_url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=True)
    session = factory()
    session.add_all([User(id=1, email="instructor@example.test", hashed_password="", role=UserRole.STAFF),
                     User(id=2, email="student@example.test", hashed_password="", role=UserRole.STUDENT, class_group="G1"),
                     User(id=3, email="other@example.test", hashed_password="", role=UserRole.STUDENT, class_group="G1")])
    session.commit()
    identity = {"id": 1}
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    @app.get("/assistance")
    def assistance():
        return {"ok": True}

    def db_override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    def user_override():
        return session.get(User, identity["id"])

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = user_override
    with TestClient(app) as client:
        yield client, session, identity, engine
    session.close()
    engine.dispose()
    if cleanup_engine:
        with cleanup_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        cleanup_engine.dispose()


@pytest.fixture
def published(environment):
    client, session, identity, engine = environment
    version_ids = []
    for prefix, difficulty in (("One", "easy"), ("Two", "medium"), ("Three", "hard")):
        created = client.post("/api/v1/admin/competition-incidents", json={"document": document(prefix, difficulty)} )
        assert created.status_code == 200, created.text
        incident_id = created.json()["id"]
        checked = client.post(f"/api/v1/admin/competition-incidents/{incident_id}/validate")
        assert checked.json()["valid"], checked.text
        approved = client.post(f"/api/v1/admin/competition-incidents/{incident_id}/approve")
        assert approved.status_code == 200, approved.text
        version_ids.append(approved.json()["version_id"])
    created = client.post("/api/v1/admin/competitions", json={"title": "Rescue joins", "description": "Practice SQL investigation.", "topic": "joins",
        "config": {"missions": version_ids}})
    assert created.status_code == 200, created.text
    comp_id = created.json()["id"]
    response = client.post(f"/api/v1/admin/competitions/{comp_id}/publish")
    assert response.status_code == 200, response.text
    identity["id"] = 2
    joined = client.post(f"/api/v1/competitions/{comp_id}/join")
    assert joined.status_code == 200, joined.text
    return client, session, identity, comp_id, joined.json()["participation_id"]
