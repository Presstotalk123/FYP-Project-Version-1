from langchain_openai import ChatOpenAI
from app.config import settings

# Per-stage config mirrors the DSL completion_params.
#
# Temperature policy: observe/normalize/grade all run at 0.0. Their job is
# extraction and adjudication, where the same submission must produce the same
# result — a student who resubmits an unchanged diagram must not get a different
# mark. Measured on a fixed observation, normalize at 0.2 produced 3 distinct
# semantic outputs in 5 trials (agreement 3/5); at 0.0 it produced 1 (5/5).
# tutor/state stay unpinned: those are conversational and benefit from variety.
# Note this reduces variance rather than guaranteeing determinism — serving-side
# batching can still perturb output.
# The DSL sends max_completion_tokens (not the legacy max_tokens, which the
# gpt-5.x families reject); model_kwargs passes it to the API verbatim on any
# langchain-openai version.
_STAGES = {
    # Pinned to match normalize/grade. observe was the only stage sampling at the
    # default temperature, and an unpinned vision read is not stable: on one and
    # the same PNG it alternated between classifying the endpoint cues as
    # sharp_arrowhead and curved_arrowhead (which invert max 1 vs max N) and
    # between finding 4 and 7 relationships. seed is best-effort on the
    # OpenAI-compatible surface — it narrows variance, it does not guarantee
    # determinism — but without it no downstream change is measurable.
    "observe":  dict(deployment=lambda: settings.ERD_AZURE_OPENAI_VISION_DEPLOYMENT,
                     params=dict(temperature=0.0, seed=42)),
    "normalize":dict(deployment=lambda: settings.ERD_AZURE_OPENAI_GRADE_DEPLOYMENT, params=dict(temperature=0.0, seed=42)),
    # max_completion_tokens must cover the WHOLE checks array plus student_message
    # plus, on the gpt-5.x families, the model's own reasoning tokens (which count
    # against this same budget). A 37-check rubric serialises to ~2200 tokens of
    # output alone, so the old 2000 cap truncated the tail of the array: the last
    # checks simply never arrived and scoring.py rendered them as
    # "Missing check result from judge output." Sized for a large rubric with
    # reasoning headroom.
    "grade":    dict(deployment=lambda: settings.ERD_AZURE_OPENAI_GRADE_DEPLOYMENT,
                     params=dict(temperature=0.0, seed=42,
                                 model_kwargs={"max_completion_tokens": 8000})),
    "tutor":    dict(deployment=lambda: settings.ERD_AZURE_OPENAI_TUTOR_DEPLOYMENT, params={}),  # gpt-5.4-nano (vision), per DSL
    "state":    dict(deployment=lambda: settings.ERD_AZURE_OPENAI_TUTOR_DEPLOYMENT, params={}),
}

def make_llm(stage: str) -> ChatOpenAI:
    cfg = _STAGES[stage]
    # Azure OpenAI's unified v1 surface ({endpoint}/openai/v1) is OpenAI-compatible:
    # deployment name goes in `model`, auth is `Authorization: Bearer <key>`, and no
    # api-version parameter exists. Current Azure resources reject all dated
    # api-versions ("API version not supported"), so the classic AzureChatOpenAI
    # deployments-path client cannot be used.
    #
    # Return the RAW client so downstream `.with_structured_output(...)` works:
    # a `.with_retry(...)`-wrapped RunnableRetry has no `with_structured_output`.
    # max_retries lives on the client itself, so it survives with_structured_output
    # (DSL parity: retry_config max_retries: 3 on the LLM nodes).
    return ChatOpenAI(
        base_url=settings.ERD_AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1",
        api_key=settings.ERD_AZURE_OPENAI_API_KEY,
        model=cfg["deployment"](),
        max_retries=3,
        timeout=settings.ERD_AZURE_OPENAI_TIMEOUT_SECONDS,
        **cfg["params"],
    )
