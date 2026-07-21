"""Response schemas for the admin ERD prompt-override endpoints.

These mirror the plain dicts returned by app.api.v1.endpoints.erd_prompts
handlers exactly (key names and optionality) so that FastAPI's response_model
serialization is byte-identical to the previous unvalidated dict responses.
"""

from typing import List, Optional
from pydantic import BaseModel


class ErdPromptVersionSummary(BaseModel):
    version_no: int
    content: str
    created_by_email: Optional[str]
    created_at: Optional[str]
    is_active: bool


class ErdPromptListItem(BaseModel):
    key: str
    label: str
    description: str
    default_content: str
    is_overridden: bool
    active: Optional[ErdPromptVersionSummary]


class ErdPromptResetResponse(BaseModel):
    key: str
    is_overridden: bool
