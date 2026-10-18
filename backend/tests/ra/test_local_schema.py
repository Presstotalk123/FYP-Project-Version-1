"""A local SQLite database created by an earlier RA commit gets the newer RA columns."""
from sqlalchemy import create_engine, inspect, text

from app.services.ra.local_schema import add_missing_columns


def test_missing_columns_are_added_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:     # ra_questions as step 3 created it, without the new column
        conn.execute(text("CREATE TABLE ra_questions (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO ra_questions (title) VALUES ('old question')"))
    add_missing_columns(engine)
    add_missing_columns(engine)      # running again changes nothing
    columns = {c["name"] for c in inspect(engine).get_columns("ra_questions")}
    assert "assessment_step_direction" in columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT assessment_step_direction FROM ra_questions")).scalar() == 0
