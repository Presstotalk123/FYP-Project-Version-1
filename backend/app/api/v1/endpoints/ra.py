"""Relational Algebra endpoints (FYP).

  GET  /ra/status                 is the module switched on? (public: the website asks
                                  before showing any RA link)
  GET  /ra/playground/examples    ready-made schemas from the lectures and Tutorial 5.5
  POST /ra/playground/run         load a schema/data, then evaluate an RA expression
  POST /ra/playground/grade       grade an answer against a model answer, with the
                                  verdict, a counterexample, step-by-step feedback and
                                  how strong the generated test databases are
  /ra/questions/…                 RA questions: see ra_questions.py

The playground is a free practice space (like RelaX): nothing is saved. Any
signed-in user may use it. The schema SQL runs in a private in-memory SQLite with file
access, PRAGMAs and long-running statements blocked (core/ra/schema.py), and the RA
answer itself never reaches SQLite. Everything except /status 404s while RA_ENABLED is off.
"""
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.core.ra import Database, EvalOptions, RAError, evaluate, parse
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.ra import (EvalOut, ExampleOut, GradeOut, PlaygroundGradeIn, PlaygroundGradeOut,
                            PlaygroundRunIn, PlaygroundRunOut, RAErrorOut, RAStatus, RelationOut,
                            SuiteSummaryOut)
from app.services.ra import grading
from app.services.ra.examples import EXAMPLES
from app.api.v1.endpoints import ra_questions

router = APIRouter(prefix="/ra", tags=["relational-algebra"])


def require_ra_enabled() -> None:
    """Dependency: 404 every RA endpoint while the module is switched off."""
    if not settings.RA_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def eval_options() -> EvalOptions:
    return EvalOptions(aggregate_nulls=settings.RA_AGGREGATE_NULLS)


@router.get("/status", response_model=RAStatus)
def get_status() -> RAStatus:
    return RAStatus(enabled=settings.RA_ENABLED, aggregate_nulls=settings.RA_AGGREGATE_NULLS)


@router.get("/playground/examples", response_model=List[ExampleOut],
            dependencies=[Depends(require_ra_enabled)])
def list_playground_examples(_user: User = Depends(get_current_user)):
    return EXAMPLES


@router.post("/playground/run", response_model=PlaygroundRunOut,
             dependencies=[Depends(require_ra_enabled)])
def run_playground(body: PlaygroundRunIn, _user: User = Depends(get_current_user)) -> PlaygroundRunOut:
    started = time.perf_counter()
    try:
        db = Database.from_sql(body.schema_sql, body.data_sql)
    except RAError as e:
        return PlaygroundRunOut(ok=False, error_source="schema", error=RAErrorOut.from_engine(e))
    relations = [RelationOut(**r) for r in db.to_dict()]
    if not body.expression.strip():
        return PlaygroundRunOut(ok=True, relations=relations, elapsed_ms=_ms(started))
    try:
        result = evaluate(parse(body.expression, db.names()), db, options=eval_options())
    except RAError as e:
        return PlaygroundRunOut(ok=False, error_source="expression", error=RAErrorOut.from_engine(e),
                                relations=relations, elapsed_ms=_ms(started))
    return PlaygroundRunOut(
        ok=True,
        relations=relations,
        result=EvalOut(columns=result.columns, rows=[list(r) for r in result.rows],
                       row_count=len(result.rows), steps=result.statements,
                       warnings=[RAErrorOut.from_engine(w) for w in result.warnings]),
        elapsed_ms=_ms(started),
    )


@router.post("/playground/grade", response_model=PlaygroundGradeOut,
             dependencies=[Depends(require_ra_enabled)])
def grade_playground(body: PlaygroundGradeIn, _user: User = Depends(get_current_user)) -> PlaygroundGradeOut:
    try:
        Database.from_sql(body.schema_sql, body.data_sql)
    except RAError as e:
        return PlaygroundGradeOut(ok=False, error_source="schema", error=RAErrorOut.from_engine(e))
    try:
        question = grading.prepared(body.schema_sql, body.model_answer, body.data_sql, options=eval_options())
    except RAError as e:
        return PlaygroundGradeOut(ok=False, error_source="model", error=RAErrorOut.from_engine(e))

    result = question.grade(body.answer)
    out = PlaygroundGradeOut(ok=True, grade=GradeOut(**result.to_dict()),
                             suite=SuiteSummaryOut(**question.suite.summary()))
    if result.verdict != "invalid_expression":
        db, source = grading.structure_database(question)
        try:
            run = evaluate(parse(body.answer, db.names()), db, options=eval_options())
        except RAError:
            return out                      # the verdict still stands; only the step trees are missing
        out.structure = EvalOut(columns=run.columns, rows=[list(r) for r in run.rows], row_count=len(run.rows),
                                steps=run.statements, warnings=[RAErrorOut.from_engine(w) for w in run.warnings])
        out.structure_source = source
        out.structure_relations = [RelationOut(**r) for r in db.to_dict()]
    return out


# RA questions: /ra/questions/… (see ra_questions.py), all behind the RA_ENABLED switch.
router.include_router(ra_questions.router, dependencies=[Depends(require_ra_enabled)])


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
