from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import erd_tutor_conversation as _erd_tutor_conversation  # noqa: F401
from app.models import er_lab_submission as _er_lab_submission  # noqa: F401

class ErdTutorMessage(Base):
    __tablename__ = "erd_tutor_messages"
    __table_args__ = (Index("ix_erd_tutor_msg_conv", "conversation_id", "created_at"),)
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("erd_tutor_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)   # user | assistant | submission
    mode = Column(String(10), nullable=False)   # query | submit
    content = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    submission_id = Column(Integer, ForeignKey("er_lab_submissions.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
