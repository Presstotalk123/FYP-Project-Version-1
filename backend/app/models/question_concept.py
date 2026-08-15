from sqlalchemy import Column, Integer, Float, ForeignKey, Index
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import question as _question  # noqa: F401
from app.models import sql_concept as _sql_concept  # noqa: F401


class QuestionConcept(Base):
    """Tags a question with a SQL concept it exercises, with an optional weight.

    ``weight`` supports questions that are mostly one concept and partly another
    (e.g. 0.7 group_by, 0.3 aggregate_functions). Staff set these tags manually in
    the question editor; there is no automated backfill. An attempt's concept
    exposure is the set of ``question_concepts`` rows for its ``question_id``.
    """
    __tablename__ = "question_concepts"
    __table_args__ = (
        Index("uq_question_concept", "question_id", "concept_id", unique=True),
        Index("ix_question_concepts_concept", "concept_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    concept_id = Column(Integer, ForeignKey("sql_concepts.id"), nullable=False)
    weight = Column(Float, nullable=False, default=1.0)
