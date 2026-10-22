"""A database created by an earlier RA commit is brought up to date at startup: newer
columns are added, and questions saved before parts existed get one part, with their
attempts linked to it."""
from sqlalchemy import create_engine, inspect, text

from app.services.ra.local_schema import add_missing_columns

# ra_questions and ra_attempts as step 3 created them (no parts, no assessment_step_direction).
OLD_TABLES = """
CREATE TABLE ra_questions (id INTEGER PRIMARY KEY, title VARCHAR(255) NOT NULL, description TEXT NOT NULL,
  difficulty VARCHAR(10) NOT NULL, schema_sql TEXT NOT NULL, data_sql TEXT NOT NULL, model_answer TEXT NOT NULL,
  checkpoints_json TEXT, show_step_direction INTEGER NOT NULL, compare_bags INTEGER NOT NULL,
  hide_correctness INTEGER NOT NULL, is_published INTEGER NOT NULL, is_deleted INTEGER NOT NULL,
  suite_json TEXT, suite_summary_json TEXT, created_by INTEGER NOT NULL, created_at DATETIME, updated_at DATETIME,
  owner_assessment_id INTEGER);
CREATE TABLE ra_attempts (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
  answer TEXT NOT NULL, verdict VARCHAR(30) NOT NULL, is_correct INTEGER NOT NULL, method VARCHAR(10),
  result_json TEXT NOT NULL, elapsed_ms INTEGER, created_at DATETIME, override_is_correct INTEGER,
  override_reason TEXT, overridden_by INTEGER, overridden_at DATETIME);
INSERT INTO ra_questions VALUES (1, 'old question', 'text', 'easy', 'CREATE TABLE R (A INTEGER)', '', 'π A R',
  '[{"statement": null, "label": "the final answer"}]', 1, 0, 0, 1, 0, '{"suite": 1}', '{"databases": 3}', 1,
  NULL, NULL, NULL);
INSERT INTO ra_attempts (user_id, question_id, answer, verdict, is_correct, result_json)
  VALUES (7, 1, 'R', 'correct', 1, '{}'), (7, 1, 'σ A > 1 R', 'wrong_in_general', 0, '{}');
"""


def test_an_old_database_is_upgraded_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        for stmt in filter(str.strip, OLD_TABLES.split(";")):
            conn.execute(text(stmt))
    add_missing_columns(engine)
    add_missing_columns(engine)      # running again changes nothing

    assert "assessment_step_direction" in {c["name"] for c in inspect(engine).get_columns("ra_questions")}
    assert "part_id" in {c["name"] for c in inspect(engine).get_columns("ra_attempts")}
    with engine.connect() as conn:
        parts = conn.execute(text(
            "SELECT id, question_id, label, marks, model_answer, checkpoints_json, suite_json FROM ra_question_parts"
        )).fetchall()
        assert len(parts) == 1
        pid, qid, label, marks, model_answer, checkpoints_json, suite_json = parts[0]
        assert (qid, label, marks, model_answer, suite_json) == (1, "", 1, "π A R", '{"suite": 1}')
        assert "the final answer" in checkpoints_json
        assert [r[0] for r in conn.execute(text("SELECT part_id FROM ra_attempts"))] == [pid, pid]
