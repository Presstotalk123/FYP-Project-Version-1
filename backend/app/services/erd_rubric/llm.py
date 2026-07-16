from langchain_openai import ChatOpenAI
from app.config import settings


def make_rubric_llm() -> ChatOpenAI:
    """Azure OpenAI unified v1 surface ({endpoint}/openai/v1, Bearer auth, no
    api-version). Grade deployment (gpt-5.4-mini), verbosity low, retries 3.
    max_completion_tokens is intentionally unset to match the Dify workflow.

    Returns the RAW client so `.with_structured_output(...)` works.
    """
    return ChatOpenAI(
        base_url=settings.AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1",
        api_key=settings.AZURE_OPENAI_API_KEY,
        model=settings.AZURE_OPENAI_GRADE_DEPLOYMENT,
        max_retries=3,
        model_kwargs={"verbosity": "low"},
    )
