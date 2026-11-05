"""The question type in the staff form (FYP). Mounted under /ra by endpoints/ra.py.

Staff, nothing saved:
  POST /ra/questions/convert-format  the type switch: every part's model answer rewritten
                                     for the new type (Mixed / Final answer / Multi-step)
  POST /ra/questions/try-steps       the multi-step preview: mark a student's boxes
                                     against the draft steps, exactly as a Submit would

Every route 404s while RA_ENABLED is off (the dependency on the parent router).
"""
from fastapi import APIRouter, Depends

from app.core.ra import Database, RAError
from app.core.ra.answer_format import MULTI_STEP, steps_from_json
from app.core.ra.grader import Checkpoint
from app.core.ra.step_marking import mark
from app.dependencies import require_staff_role
from app.models.user import User
from app.schemas.ra import (GradeOut, RAConvertPartOut, RAErrorOut, RAFormatConvertIn, RAFormatConvertOut,
                            RATryStepsIn, RATryStepsOut, StepMarkingOut)
from app.services.ra import formats, grading, multi_step, questions as svc

router = APIRouter(prefix="/questions")


@router.post("/convert-format", response_model=RAFormatConvertOut)
def convert_format(body: RAFormatConvertIn, _staff: User = Depends(require_staff_role)):
    """Rewrite every part for the new type. A part that can't be converted keeps its text,
    with an ``error`` asking staff to rewrite it."""
    parts = [dict(model_answer=p.model_answer, marks=p.marks,
                  checkpoints=[c.model_dump() for c in p.checkpoints] if p.checkpoints else None,
                  steps=[s.model_dump() for s in p.steps] if p.steps is not None else None) for p in body.parts]
    try:
        converted = formats.convert(body.schema_sql, body.from_format, body.to_format, parts)
    except RAError as e:
        return RAFormatConvertOut(ok=False, error=RAErrorOut.from_engine(e))
    return RAFormatConvertOut(ok=True, parts=[RAConvertPartOut(**p) for p in converted])


@router.post("/try-steps", response_model=RATryStepsOut)
def try_steps(body: RATryStepsIn, _staff: User = Depends(require_staff_role)):
    """Mark boxes against draft steps (the form's student preview), with the question's
    settings, on the data students would see."""
    try:
        schema = Database.from_sql(body.schema_sql)
    except RAError as e:
        return RATryStepsOut(ok=False, error_source="schema", error=RAErrorOut.from_engine(e))
    spec = dict(steps=[s.model_dump() for s in body.steps], model_answer="", marks=1, checkpoints=None)
    try:
        spec = formats.part_spec(MULTI_STEP, spec, 0, schema, svc.eval_options())
    except formats.FormatError as e:
        return RATryStepsOut(ok=False, error_source="steps", error=RAErrorOut.from_engine(e.error), error_step=e.step)
    if (body.data_sql or "").strip():
        try:
            Database.from_sql(body.schema_sql, body.data_sql)
        except RAError as e:
            return RATryStepsOut(ok=False, error_source="data", error=RAErrorOut.from_engine(e))
    # The checkpoints are the steps' prompts (answer_format.steps_checkpoints).
    cps = [Checkpoint(c["statement"], c["label"]) for c in spec["checkpoints"]]
    try:
        prepared = grading.prepared(body.schema_sql, spec["model_answer"], body.data_sql,
                                    options=svc.eval_options(), checkpoints=cps, bag=body.compare_bags)
    except RAError as e:
        return RATryStepsOut(ok=False, error_source="steps", error=RAErrorOut.from_engine(e))
    steps = steps_from_json(spec["steps"])
    answers = multi_step.padded(steps, body.step_answers)
    marking = mark(prepared, steps, answers)
    shown_db, source = None, None
    if (body.data_sql or "").strip():
        shown_db, source = prepared.sample, "sample"
    elif body.example_data_sql and svc.fits_schema(body.schema_sql, body.example_data_sql):
        shown_db, source = Database.from_sql(body.schema_sql, body.example_data_sql), "example"
    else:
        shown_db, source = grading.structure_database(prepared)
    rows = multi_step.step_results(prepared, steps, answers, marking, shown_db, direction=True)
    return RATryStepsOut(ok=True, grade=GradeOut(**marking.grade.to_dict()),
                         marking=StepMarkingOut(earned=marking.earned, total=marking.total,
                                                final_correct=marking.grade.correct, source=source, steps=rows))
