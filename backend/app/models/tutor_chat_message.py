from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import tutor_chat_conversation as _tutor_chat_conversation  # noqa: F401


class TutorChatMessage(Base):
    __tablename__ = "tutor_chat_messages"
    __table_args__ = (Index("ix_tutor_chat_msg_conv", "conversation_id", "created_at"),)
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("tutor_chat_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)   # user | assistant
    content = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
