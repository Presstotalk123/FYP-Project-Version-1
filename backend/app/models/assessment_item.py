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

    assessment = relationship("Assessment", back_populates="items")
