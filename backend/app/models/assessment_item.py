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
    # When the assessment is published, item_id is repointed to a frozen content clone and
    # source_item_id holds the original master content id (used for idempotent re-publish
    # and to restore the master pointer on unpublish). NULL while unpublished.
    source_item_id = Column(Integer, nullable=True)

    assessment = relationship("Assessment", back_populates="items")
