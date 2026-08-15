from sqlalchemy import Column, Integer, ForeignKey, Index
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import sql_concept as _sql_concept  # noqa: F401


class SqlConceptPrerequisite(Base):
    """A directed prerequisite edge in the concept DAG: ``prerequisite_concept_id``
    should be learned before ``concept_id``. Kept as a normalized edge table (not a
    JSON adjacency list) since the graph is queried relationally by the mastery
    logic and the LAD dependency-graph payload.
    """
    __tablename__ = "sql_concept_prerequisites"
    __table_args__ = (
        Index(
            "uq_sql_concept_prereq", "concept_id", "prerequisite_concept_id",
            unique=True,
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    concept_id = Column(Integer, ForeignKey("sql_concepts.id"), nullable=False, index=True)
    prerequisite_concept_id = Column(Integer, ForeignKey("sql_concepts.id"), nullable=False, index=True)
