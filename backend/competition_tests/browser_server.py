"""Disposable local browser-test server. Never imported by the production app.

Uses the real Competition router/services and signed JWT authentication. Its
database and fixtures are confined to a temporary directory, removed on exit.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from contextlib import asynccontextmanager

scratch = tempfile.TemporaryDirectory(prefix="rescue-browser-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(scratch.name) / "metadata.db")
os.environ["SECRET_KEY"] = "local-browser-tests-only-not-production"
os.environ["COMPETITIONS_ENABLED"] = "True"
os.environ["COMPETITION_DB_PATH"] = str(Path(scratch.name) / "fixtures")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints.competitions import router
from app.core.security import create_access_token
from app.database import Base, engine, SessionLocal
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.competition import Competition, CompetitionIncident, CompetitionIncidentVersion
from app.core.competition_executor import digest
from app.services.incident_authoring import validate_document, PARSER_VERSION


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add_all([User(id=1, email="staff@rescue.test", hashed_password="", role=UserRole.ADMIN),
                    User(id=2, email="student@rescue.test", hashed_password="", role=UserRole.STUDENT, class_group="G1")])
        db.commit()
        definitions = json.loads((Path(__file__).resolve().parents[1] / "app/data/database_rescue_slides.json").read_text(encoding="utf-8"))
        versions = []
        for definition in definitions:
            doc = definition["document"]
            doc["oracle_confirmed"] = True  # Synthetic rehearsal only; never updates the manifest.
            checked = validate_document(doc)
            if not checked["valid"]:
                raise RuntimeError(str(checked["errors"]))
            incident = CompetitionIncident(title=doc["title"], document=doc, created_by=1, status="approved")
            db.add(incident); db.flush()
            version = CompetitionIncidentVersion(incident_id=incident.id, document=doc, content_hash=digest(doc), parser_version=PARSER_VERSION, approved_by=1)
            db.add(version); db.flush(); versions.append(version.id)
        db.add(Competition(id=1, title="Database Rescue: Joins", description="Investigate the Easy and Medium incidents from the presentation. Restore the student directory (10 points) and support dashboard (20 points).", topic="joins", published=1, content_hash=digest(definitions), created_by=1,
                           config={"missions": versions, "class_groups": [], "leaderboard": True, "time_tiebreak": True, "points": {"easy": 10, "medium": 20, "hard": 30}}))
        db.commit()
    yield
    engine.dispose()
    scratch.cleanup()


app = FastAPI(lifespan=lifespan)
web_port = int(os.environ.get("RESCUE_TEST_WEB_PORT", "3017"))
app.add_middleware(CORSMiddleware, allow_origins=[f"http://127.0.0.1:{web_port}"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/test-token/{role}")
def token(role: str):
    email = "staff@rescue.test" if role == "staff" else "student@rescue.test"
    return {"token": create_access_token({"sub": email})}


@app.get("/api/v1/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "role": user.role.value, "is_active": True, "created_at": user.created_at}


@app.post("/api/v1/chatbot/course-chat")
def assistance():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("RESCUE_TEST_API_PORT", "8017")), log_level="warning")
