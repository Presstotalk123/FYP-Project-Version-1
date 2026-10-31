"""Database Rescue records. Published documents and submitted reports are snapshots."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class CompetitionSource(Base):
    __tablename__ = "competition_sources"
    __table_args__ = (UniqueConstraint("provider", "external_id", "content_hash"),)
    id = Column(Integer, primary_key=True)
    provider = Column(String(40), nullable=False)
    external_id = Column(String(100), nullable=False)
    content_hash = Column(String(64), nullable=False)
    snapshot = Column(JSON, nullable=False)
    diagnostics = Column(JSON, nullable=False, default=list)
    authorised = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionIncident(Base):
    __tablename__ = "competition_incidents"
    id = Column(Integer, primary_key=True)
    origin_key = Column(String(100), unique=True)
    source_id = Column(Integer, ForeignKey("competition_sources.id"))
    title = Column(String(255), nullable=False)
    document = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    revision = Column(Integer, nullable=False, default=1)
    validation = Column(JSON)
    validated_hash = Column(String(64))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionIncidentVersion(Base):
    __tablename__ = "competition_incident_versions"
    __table_args__ = (UniqueConstraint("incident_id", "content_hash"),)
    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("competition_incidents.id"), nullable=False)
    content_hash = Column(String(64), nullable=False)
    document = Column(JSON, nullable=False)
    source_id = Column(Integer, ForeignKey("competition_sources.id"))
    parser_version = Column(String(100), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Competition(Base):
    __tablename__ = "competitions"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    topic = Column(String(100), nullable=False)
    config = Column(JSON, nullable=False)
    published = Column(Integer, nullable=False, default=0)
    content_hash = Column(String(64))
    opens_at = Column(DateTime(timezone=True))
    closes_at = Column(DateTime(timezone=True))
    feedback_released = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionParticipation(Base):
    __tablename__ = "competition_participations"
    __table_args__ = (UniqueConstraint("competition_id", "user_id"),)
    id = Column(Integer, primary_key=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    cohort = Column(String(100), nullable=False, default="")
    # Retained legacy columns keep existing databases readable without deleting history.
    form_order = Column(String(2), nullable=False, default="")
    phase = Column(String(20), nullable=False, default="gameplay")
    phase_active = Column(Integer, nullable=False, default=0)
    pre_submitted_at = Column(DateTime(timezone=True))
    post_submitted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionDraft(Base):
    __tablename__ = "competition_drafts"
    __table_args__ = (UniqueConstraint("participation_id", "item_key"),)
    id = Column(Integer, primary_key=True)
    participation_id = Column(Integer, ForeignKey("competition_participations.id"), nullable=False)
    item_key = Column(String(40), nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    payload = Column(JSON, nullable=False, default=dict)
    help_level = Column(Integer, nullable=False, default=0)
    submitted = Column(Integer, nullable=False, default=0)
    restored = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CompetitionRun(Base):
    __tablename__ = "competition_runs"
    id = Column(Integer, primary_key=True)
    participation_id = Column(Integer, ForeignKey("competition_participations.id"), nullable=False, index=True)
    item_key = Column(String(40), nullable=False)
    kind = Column(String(20), nullable=False)
    component_id = Column(String(60))
    sql = Column(Text, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionSubmission(Base):
    __tablename__ = "competition_submissions"
    __table_args__ = (UniqueConstraint("participation_id", "request_key"),)
    id = Column(Integer, primary_key=True)
    participation_id = Column(Integer, ForeignKey("competition_participations.id"), nullable=False, index=True)
    item_key = Column(String(40), nullable=False)
    request_key = Column(String(80), nullable=False)
    incident_version_id = Column(Integer, ForeignKey("competition_incident_versions.id"), nullable=False)
    draft_revision = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)
    help_level = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    result = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    graded_at = Column(DateTime(timezone=True))


class CompetitionEvent(Base):
    __tablename__ = "competition_events"
    id = Column(Integer, primary_key=True)
    participation_id = Column(Integer, ForeignKey("competition_participations.id"), nullable=False, index=True)
    item_key = Column(String(40))
    event_type = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionReward(Base):
    __tablename__ = "competition_rewards"
    __table_args__ = (UniqueConstraint("participation_id", "item_key", "kind"),)
    id = Column(Integer, primary_key=True)
    participation_id = Column(Integer, ForeignKey("competition_participations.id"), nullable=False, index=True)
    item_key = Column(String(40), nullable=False)
    kind = Column(String(40), nullable=False)
    xp = Column(Integer, nullable=False)
    submission_id = Column(Integer, ForeignKey("competition_submissions.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionReview(Base):
    __tablename__ = "competition_reviews"
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("competition_submissions.id"), nullable=False, index=True)
    diagnosis_score = Column(Integer, nullable=False)
    explanation_score = Column(Integer, nullable=False)
    rationale = Column(Text, nullable=False)
    rubric_version = Column(String(30), nullable=False, default="rescue-v1")
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetitionExecutionLease(Base):
    __tablename__ = "competition_execution_leases"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    token = Column(String(40), nullable=False, default="")
    expires_at = Column(DateTime(timezone=True), nullable=False)


class CompetitionSurvey(Base):
    __tablename__ = "competition_surveys"
    participation_id = Column(Integer, ForeignKey("competition_participations.id"), primary_key=True)
    response = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
