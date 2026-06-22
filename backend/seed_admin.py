"""
Seed script: creates an admin whitelist entry and user record.
Run from the backend directory: python seed_admin.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
from app.models.user import User, UserRole
from app.models.whitelist import WhitelistEntry

ADMIN_EMAIL = "thangatharunponmurugu@gmail.com"


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Whitelist entry
        existing_wl = db.query(WhitelistEntry).filter(WhitelistEntry.email == ADMIN_EMAIL).first()
        if existing_wl:
            existing_wl.role = UserRole.ADMIN
            print(f"Updated whitelist entry for {ADMIN_EMAIL} to ADMIN")
        else:
            db.add(WhitelistEntry(email=ADMIN_EMAIL, role=UserRole.ADMIN))
            print(f"Created whitelist entry for {ADMIN_EMAIL} as ADMIN")

        # User record
        existing_user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing_user:
            existing_user.role = UserRole.ADMIN
            existing_user.is_active = 1
            print(f"Updated user {ADMIN_EMAIL} to ADMIN")
        else:
            db.add(User(
                email=ADMIN_EMAIL,
                hashed_password="",  # Google OAuth — no password needed
                role=UserRole.ADMIN,
                is_active=1,
            ))
            print(f"Created user {ADMIN_EMAIL} as ADMIN")

        db.commit()
        print("Done. You can now log in with Google using that email.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
