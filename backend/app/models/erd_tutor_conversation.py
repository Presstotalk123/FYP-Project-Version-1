from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401
from app.models import er_diagram_question as _er_diagram_question  # noqa: F401

class ErdTutorConversation(Base):
    __tablename__ = "erd_tutor_conversations"
    __table_args__ = (
        Index("ix_erd_tutor_conv_standalone", "user_id", "er_diagram_question_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    er_diagram_question_id = Column(Integer, ForeignKey("er_diagram_questions.id"), nullable=True)
    context_type = Column(String(20), nullable=False)  # "standalone"
    # state snapshot (cv_*)
    ibl_stage = Column(String(40), nullable=False, default="orientation")
    hint_level = Column(Integer, nullable=False, default=1)
    misconceptions = Column(Text, nullable=True)        # JSON array
    current_erd_model = Column(Text, nullable=True)     # JSON object
    last_submit_report = Column(Text, nullable=True)    # JSON object
    last_submit_score = Column(Text, nullable=True)     # JSON object
    last_query_summary = Column(Text, nullable=True)
    last_student_goal = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
