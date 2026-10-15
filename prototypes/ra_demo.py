"""Relational-algebra demo: translate RA to SQL, run it, and show the tree and result.

Uses the real translator in backend/app/core/ra and the platform's read-only executor,
against the sample university database from the test suite.

    cd backend
    python ../prototypes/ra_demo.py                       # run the built-in examples
    python ../prototypes/ra_demo.py "π[name](Student)"    # translate your own expression
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("SECRET_KEY", "demo-only")

from app.core.query_executor import execute_student_query  # noqa: E402
from app.core.ra import RAError, Schema, translate  # noqa: E402
from tests.fyp.ra_fixtures import build_university_db  # noqa: E402

EXAMPLES = [
    ("Names of CS students older than 20",
     "π[name](σ[age > 20 ∧ major = 'CS'](Student))"),
    ("Students enrolled in every CS course (division)",
     "π[name](Student ⋈ (π[sid, cid](Enrolled) ÷ π[cid](σ[dept = 'CS'](Course))))"),
    ("Students not enrolled in any course (difference)",
     "π[name](Student) − π[name](Student ⋈ Enrolled)"),
    ("Same thing, ASCII notation",
     "\\project_{name} Student \\diff \\project_{name} (Student \\join Enrolled)"),
    ("A typo — RA-level error message",
     "π[nme](Student)"),
    ("Projecting an ambiguous attribute after ×",
     "π[sid](Student × Enrolled)"),
]


def show_tree(node, indent=""):
    print(f"{indent}{node['label']:<34} → ({', '.join(node['schema'])})")
    for child in node["children"]:
        show_tree(child, indent + "    ")


def demo(title, expr, db, schema):
    print("=" * 78)
    print(title)
    print("  RA :", expr)
    try:
        tr = translate(expr, schema)
    except RAError as e:
        print(f"  ✗ {e.code}: {e}")
        return
    print("  Tree:")
    show_tree(tr.tree, "    ")
    print("  SQL:", tr.sql if len(tr.sql) < 200 else tr.sql[:200] + " …")
    for w in tr.warnings:
        print(f"  ⚠ {w.code}: {w}")
    result = execute_student_query(db, tr.sql)
    if not result["success"]:
        print("  ✗ executor:", result["error_message"])
        return
    print(f"  Result ({result['row_count']} tuples): ", [tuple(r.values()) for r in result["results"]])


def main():
    db = build_university_db(os.path.join(tempfile.mkdtemp(), "university.db"))
    schema = Schema.from_sqlite(db)
    if len(sys.argv) > 1:
        demo("Your expression", sys.argv[1], db, schema)
    else:
        for title, expr in EXAMPLES:
            demo(title, expr, db, schema)


if __name__ == "__main__":
    main()
