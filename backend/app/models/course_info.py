from sqlalchemy import Column, Integer, Text
from app.database import Base


class CourseInfo(Base):
    """Singleton row holding the student-facing course syllabus as Markdown.

    Only one row ever exists (id == 1). Staff edit it from the Settings page;
    students read the rendered Markdown on the Course Info page. When no row
    exists yet, the read endpoint falls back to DEFAULT_COURSE_INFO_MD so the
    page is never empty before the first save.
    """
    __tablename__ = "course_info"

    id = Column(Integer, primary_key=True)              # always 1
    content = Column(Text, nullable=False)              # Markdown
