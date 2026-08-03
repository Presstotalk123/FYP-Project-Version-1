from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class AssessmentItem(Base):
    """
    Polymorphic junction linking an assessment to any content type.
    item_type: 'sql_question' | 'er_question' | 'sql_lab' | 'graph_lab'
    item_id:   PK in the corresponding table
    """
    __tablename__ = "assessment_items"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    item_type = Column(String(30), nullable=False)
    item_id = Column(Integer, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    # Integer percentage (0-100) of the assessment total for this item. Weights across an
    # assessment's items must total 100 (enforced in the API layer / editor). 0 = legacy/unweighted.
    weight = Column(Integer, default=0, nullable=False)
    # Per-item override written onto the content clone at publish time (see assessment_clone).
    # 0/1 flag. 0 = students see correctness feedback (default); 1 = neutral "Submitted" only.
    # Applies to sql_question / sql_lab / graph_lab; ignored for er_question.
    hide_correctness = Column(Integer, default=0, nullable=False)
    # Per-item cap on how many queries a student may run on this SQL question during the
    # assessment. NULL = unlimited (default). Only meaningful for sql_question items; enforced
    # at runtime in the execute endpoint against UserProgress.attempts_count.
    max_queries = Column(Integer, nullable=True)
    # When the assessment is published, item_id is repointed to a frozen content clone and
    # source_item_id holds the original master content id (used for idempotent re-publish
    # and to restore the master pointer on unpublish). NULL while unpublished.
    source_item_id = Column(Integer, nullable=True)

    assessment = relationship("Assessment", back_populates="items")
