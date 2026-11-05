"""Explicit draft import: python -m scripts.import_normalization_starters --created-by STAFF_ID."""
import argparse

from app.database import SessionLocal
from app.data.normalization_starters import QUESTION_SEEDS
from app.models.normalization import NormalizationQuestion
from app.models.user import User, UserRole
from app.services.normalization.questions import validate_reference


def import_starters(db, owner_id):
    user = db.get(User, owner_id)
    if not user or user.role not in {UserRole.STAFF, UserRole.ADMIN}:
        raise ValueError("--created-by must identify an existing staff or admin account")
    inserted = 0
    for seed in QUESTION_SEEDS:
        if db.query(NormalizationQuestion.id).filter_by(source_slug=seed["id"]).first():
            continue
        q = NormalizationQuestion(source_slug=seed["id"], created_by=owner_id,
            title=seed["title"], difficulty=seed["difficulty"], scenario=seed["scenario"],
            relation_name=seed["relation_name"], attributes=seed["attributes"], statements=seed["statements"],
            sample_rows=seed["sample_rows"], approved_fds=seed["fds"], target_normal_form=seed["target_normal_forms"][0],
            is_published=0, semantic_judge_enabled=0)
        validate_reference(q)
        db.add(q)
        inserted += 1
    db.commit()
    return inserted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--created-by", type=int, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        print(f"Imported {import_starters(db, args.created_by)} draft questions")
