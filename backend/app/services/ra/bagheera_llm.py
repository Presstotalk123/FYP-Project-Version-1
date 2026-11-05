"""The one call Bagheera makes to the AI provider for RA: a whole reply, not streamed.

RA replies are checked by the leak guard before they are shown (bagheera.py), so there
is nothing to stream. The provider is the platform's (``AI_PROVIDER``: azure_openai,
openai or gemini, with ``AI_MODEL`` and ``AI_API_KEY``), as for the SQL tutor.
Tests replace ``complete``.
"""
from typing import Dict, List

from app.config import settings

TIMEOUT_SECONDS = 30


class TutorUnavailable(Exception):
    """The AI provider isn't set up or didn't answer."""


def configured() -> bool:
    return bool((settings.AI_API_KEY or "").strip())


async def complete(system: str, messages: List[Dict[str, str]]) -> str:
    """messages: [{"role": "user" | "assistant", "content": …}], oldest first."""
    if not configured():
        raise TutorUnavailable("Bagheera isn't set up on this server.")
    provider = (settings.AI_PROVIDER or "").lower()
    try:
        if provider in ("azure_openai", "openai"):
            from openai import AsyncAzureOpenAI, AsyncOpenAI
            client = (AsyncAzureOpenAI(api_key=settings.AI_API_KEY, azure_endpoint=settings.AI_AZURE_ENDPOINT,
                                       api_version=settings.AI_AZURE_API_VERSION)
                      if provider == "azure_openai" else AsyncOpenAI(api_key=settings.AI_API_KEY))
            kwargs = {"model": settings.AI_MODEL, "timeout": TIMEOUT_SECONDS,
                      "messages": [{"role": "system", "content": system}, *messages]}
            if settings.AI_ENABLE_TEMPERATURE:
                kwargs["temperature"] = settings.AI_TEMPERATURE if settings.AI_TEMPERATURE is not None else 0.4
            response = await client.chat.completions.create(**kwargs)
            return (response.choices[0].message.content or "").strip()
        if provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=settings.AI_API_KEY)
            model = genai.GenerativeModel(model_name=settings.AI_MODEL, system_instruction=system)
            history = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]}
                       for m in messages[:-1]]
            chat = model.start_chat(history=history)
            response = await chat.send_message_async(messages[-1]["content"])
            return (response.text or "").strip()
    except Exception as e:                      # the provider's own errors vary by SDK
        raise TutorUnavailable(f"Bagheera couldn't be reached ({type(e).__name__}).") from e
    raise TutorUnavailable(f"Unsupported AI_PROVIDER: {provider}")
