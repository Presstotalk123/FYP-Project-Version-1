from langchain_openai import ChatOpenAI
from app.config import settings


def make_rubric_llm() -> ChatOpenAI:
    """Azure OpenAI unified v1 surface ({endpoint}/openai/v1, Bearer auth, no
    api-version). Vision deployment (gpt-5.4), verbosity low, retries 3.
    max_completion_tokens is intentionally unset to match the Dify workflow.

    Vision, not grade: the model answer arrives as an image and the rubric must
    reproduce it exactly. On the grade deployment (gpt-5.4-mini) every run broke
    a different rule of RUBRIC_SYSTEM — keys the image does not draw, ISA written
    as a relationship, double diamonds miscounted, labels misread. One call per
    rubric, staff-side, so the larger model costs little.

    Returns the RAW client so `.with_structured_output(...)` works.
    """
    return ChatOpenAI(
        base_url=settings.ERD_AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1",
        api_key=settings.ERD_AZURE_OPENAI_API_KEY,
        model=settings.ERD_AZURE_OPENAI_VISION_DEPLOYMENT,
        max_retries=3,
        timeout=settings.ERD_RUBRIC_TIMEOUT_SECONDS,
        model_kwargs={"verbosity": "low"},
    )
