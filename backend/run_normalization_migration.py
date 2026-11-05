"""Create the additive normalization tables on SQLite or PostgreSQL. Safe to re-run."""
from app.database import engine
from app.models.normalization import NormalizationQuestion, NormalizationSubmission, NormalizationReview


def main():
    for model in (NormalizationQuestion, NormalizationSubmission, NormalizationReview):
        model.__table__.create(engine, checkfirst=True)
        print(f"{model.__tablename__}: ready")


if __name__ == "__main__":
    main()
