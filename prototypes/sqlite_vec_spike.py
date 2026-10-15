"""sqlite-vec feasibility spike (FYP Design Document 03, risk R1).

Answers four questions with real runs of the "Hawker flavour space" sample lab:
  1. Can this Python load SQLite extensions at all?
  2. Do sqlite-vec's scalar functions and the vec0 k-NN table work on that lab?
  3. Do the results match the expected answers worked out in Design Document 03 §5.2?
  4. Can a pure-Python fallback (no extension) reproduce the scalar-function tasks?

    pip install sqlite-vec
    python prototypes/sqlite_vec_spike.py
"""
import json
import math
import platform
import sqlite3
import sys

SEED = """
CREATE TABLE foods (id INTEGER PRIMARY KEY, name TEXT NOT NULL, cuisine TEXT NOT NULL,
                    embedding TEXT NOT NULL);  -- [sweet, salty, spicy, sour]
INSERT INTO foods VALUES
 (1,'Mango sticky rice','Thai','[0.90,0.20,0.00,0.10]'),
 (2,'Tom yum soup','Thai','[0.10,0.40,0.80,0.70]'),
 (3,'Laksa','Malaysian','[0.20,0.50,0.70,0.30]'),
 (4,'Kaya toast','Singaporean','[0.80,0.30,0.00,0.00]'),
 (5,'Salted egg chips','Singaporean','[0.10,0.90,0.20,0.00]'),
 (6,'Mala hotpot','Chinese','[0.10,0.60,0.95,0.20]'),
 (7,'Chendol','Malaysian','[0.95,0.10,0.00,0.00]'),
 (8,'Sambal stingray','Malaysian','[0.10,0.60,0.80,0.30]'),
 (9,'Achar','Malaysian','[0.05,0.15,0.45,0.30]');
CREATE TABLE queries (name TEXT PRIMARY KEY, embedding TEXT NOT NULL);
INSERT INTO queries VALUES ('craving_spicy_sour','[0.10,0.30,0.90,0.60]'),
                           ('dessert','[1.00,0.10,0.00,0.00]');
"""
SEED_VEC0 = """
CREATE VIRTUAL TABLE foods_vec USING vec0(embedding float[4]);
INSERT INTO foods_vec(rowid, embedding) SELECT id, embedding FROM foods;
"""

TASKS = {
    "T1 dimensions": ("SELECT DISTINCT vec_length(embedding) FROM foods", [(4,)]),
    "T2 L2 top-3": (
        "SELECT f.name, ROUND(vec_distance_l2(f.embedding, q.embedding), 4) AS d "
        "FROM foods f, queries q WHERE q.name = 'craving_spicy_sour' ORDER BY d LIMIT 3",
        [("Tom yum soup", 0.1732), ("Laksa", 0.4243), ("Sambal stingray", 0.4359)]),
    "T3 cosine top-3": (
        "SELECT f.name, ROUND(vec_distance_cosine(f.embedding, q.embedding), 4) AS d "
        "FROM foods f, queries q WHERE q.name = 'craving_spicy_sour' ORDER BY d LIMIT 3",
        [("Achar", 0.0), ("Tom yum soup", 0.0116), ("Laksa", 0.0677)]),
    "T4 hybrid": (
        "SELECT f.name, ROUND(vec_distance_l2(f.embedding, q.embedding), 4) AS d "
        "FROM foods f, queries q WHERE q.name = 'dessert' AND f.cuisine = 'Malaysian' "
        "ORDER BY d LIMIT 2",
        [("Chendol", 0.05), ("Achar", 1.0943)]),
}
VEC0_TASK = (
    "SELECT rowid FROM foods_vec WHERE embedding MATCH "
    "(SELECT embedding FROM queries WHERE name = 'dessert') AND k = 3 ORDER BY distance",
    [(7,), (1,), (4,)])


def python_fallback(conn):
    """Same function names, implemented in Python (no extension needed)."""
    def vec(text):
        return json.loads(text)

    def l2(a, b):
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(vec(a), vec(b))))

    def cosine(a, b):
        a, b = vec(a), vec(b)
        dot = sum(x * y for x, y in zip(a, b))
        return 1 - dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))

    conn.create_function("vec_length", 1, lambda a: len(vec(a)), deterministic=True)
    conn.create_function("vec_distance_l2", 2, l2, deterministic=True)
    conn.create_function("vec_distance_cosine", 2, cosine, deterministic=True)


def normalise(rows):
    """The planned VectorQueryExecutor normalisation: 4 dp, and -0.0 → 0.0."""
    out = []
    for row in rows:
        out.append(tuple((round(v, 4) + 0.0) if isinstance(v, float) else v for v in row))
    return out


def check(conn, label, sql, expected):
    rows = conn.execute(sql).fetchall()
    raw_negative_zero = any(isinstance(v, float) and v == 0 and math.copysign(1, v) < 0
                            for row in rows for v in row)
    ok = normalise(rows) == expected
    note = "   (raw result contained -0.0; normalised)" if raw_negative_zero else ""
    print(f"  {'✔' if ok else '✗'} {label:<18} {normalise(rows)}{note}")
    return ok


def main():
    print(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}, "
          f"SQLite {sqlite3.sqlite_version}")
    conn = sqlite3.connect(":memory:")
    can_load = hasattr(conn, "enable_load_extension")
    print(f"1. Extension loading available: {can_load}")

    results = []
    if can_load:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        version = conn.execute("SELECT vec_version()").fetchone()[0]
        print(f"2. sqlite-vec {version} loaded; extension loading switched off again")
        try:
            conn.execute("SELECT load_extension('anything')")
            print("   ✗ student SQL could still call load_extension()")
            results.append(False)
        except sqlite3.OperationalError as e:
            print(f"   ✔ load_extension() from SQL is refused: {e}")
        conn.executescript(SEED + SEED_VEC0)
        print("3. sqlite-vec results vs Design Document 03 §5.2:")
        for label, (sql, expected) in TASKS.items():
            results.append(check(conn, label, sql, expected))
        results.append(check(conn, "T5 vec0 k-NN", *VEC0_TASK))
    else:
        print("   → sqlite-vec cannot be used with this Python build; only the fallback applies.")

    print("4. Pure-Python fallback (scalar-function tasks):")
    fb = sqlite3.connect(":memory:")
    python_fallback(fb)
    fb.executescript(SEED)
    for label, (sql, expected) in TASKS.items():
        results.append(check(fb, label, sql, expected))

    print(f"\n{'ALL CHECKS PASSED' if all(results) else 'SOME CHECKS FAILED'} ({sum(results)}/{len(results)})")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
