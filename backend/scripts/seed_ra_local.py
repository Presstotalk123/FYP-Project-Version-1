"""Set up a LOCAL database for trying the Relational Algebra module.

  * whitelists your Google email as admin (sign-in is refused for emails that are not
    whitelisted), and optionally a second email as a student;
  * adds the SC2207 Tutorial 5.5 questions (and one lecture example with data) as
    published RA questions, building their test databases.

Run it from ``backend/`` (it reads backend/.env like the server):

    ../.venv/bin/python scripts/seed_ra_local.py --admin-email you@gmail.com
    ../.venv/bin/python scripts/seed_ra_local.py --admin-email you@gmail.com --student-email other@gmail.com

Refuses to run unless DATABASE_URL is a SQLite file, so it can never write to the
production PostgreSQL database. Safe to re-run: existing entries and questions (matched
by title) are left as they are.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401  (registers every table for create_all)
from app.models.ra_question import RAQuestion  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.models.whitelist import WhitelistEntry  # noqa: E402
from app.services.ra import questions as svc  # noqa: E402
from app.services.ra.local_schema import add_missing_columns  # noqa: E402
from app.services.ra.tutorial_5_5 import QUESTIONS  # noqa: E402


def whitelist(db, email: str, role: UserRole) -> User:
    entry = db.query(WhitelistEntry).filter(WhitelistEntry.email == email).first()
    if entry is None:
        db.add(WhitelistEntry(email=email, role=role))
        print(f"  whitelisted {email} as {role.value}")
    else:
        print(f"  {email} already whitelisted (as {entry.role.value}); left unchanged")
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, hashed_password="", role=role)
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_questions(db, author: User) -> None:
    for spec in QUESTIONS:
        exists = db.query(RAQuestion).filter(RAQuestion.title == spec["title"], RAQuestion.is_deleted == 0).first()
        if exists:
            print(f"  exists   #{exists.id} {spec['title']}")
            continue
        q = RAQuestion(title=spec["title"], description=spec["description"], difficulty=spec["difficulty"],
                       schema_sql="", data_sql="", model_answer="", is_published=1, created_by=author.id)
        db.add(q)
        db.flush()
        parts = spec.get("parts") or [{"model_answer": spec["model_answer"]}]
        prepared = svc.save_content(db, q, schema_sql=spec["schema_sql"], data_sql=spec.get("data_sql", ""),
                                    parts=parts, compare_bags=False)
        db.commit()
        caught = ", ".join(f"{p.suite.summary()['mutants_killed']}/{p.suite.summary()['mutants']}" for p in prepared)
        print(f"  created  #{q.id} {spec['title']}  ({len(prepared)} part(s); wrong versions caught: {caught})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--admin-email", required=True, help="your Google account email (made admin)")
    parser.add_argument("--student-email", help="a second Google account to sign in as a student")
    parser.add_argument("--no-questions", action="store_true", help="only whitelist, don't add questions")
    args = parser.parse_args()

    if not settings.DATABASE_URL.startswith("sqlite"):
        sys.exit("Refusing to run: DATABASE_URL is not a local SQLite database.")
    for email in filter(None, [args.admin_email, args.student_email]):
        if "@" not in email or "." not in email.split("@", 1)[1]:
            sys.exit(f"{email!r} is not a valid email (the app needs a dot after the @).")

    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine)
    db = SessionLocal()
    try:
        print("Whitelist:")
        admin = whitelist(db, args.admin_email.strip().lower(), UserRole.ADMIN)
        if args.student_email:
            whitelist(db, args.student_email.strip().lower(), UserRole.STUDENT)
        if not args.no_questions:
            print("RA questions:")
            seed_questions(db, admin)
    finally:
        db.close()
    print("\nDone. Make sure backend/.env has RA_ENABLED=true, restart the backend, then sign in at "
          "http://localhost:3000.")


if __name__ == "__main__":
    main()
