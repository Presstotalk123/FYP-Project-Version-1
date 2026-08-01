from langchain_openai import ChatOpenAI
from app.config import settings

# Per-stage config mirrors the DSL completion_params.
# The DSL sends max_completion_tokens (not the legacy max_tokens, which the
# gpt-5.x families reject); model_kwargs passes it to the API verbatim on any
# langchain-openai version.
_STAGES = {
    "observe":  dict(deployment=lambda: settings.ERD_AZURE_OPENAI_VISION_DEPLOYMENT, params={}),
    "normalize":dict(deployment=lambda: settings.ERD_AZURE_OPENAI_GRADE_DEPLOYMENT, params=dict(temperature=0.2, seed=42)),
    "grade":    dict(deployment=lambda: settings.ERD_AZURE_OPENAI_GRADE_DEPLOYMENT,
                     params=dict(temperature=0.2, seed=42,
                                 model_kwargs={"max_completion_tokens": 2000})),
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
        **cfg["params"],
    )
