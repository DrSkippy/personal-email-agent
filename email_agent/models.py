"""Pydantic models shared across the email agent."""

from typing import Literal, Optional
from pydantic import BaseModel


Category = Literal["Advertising", "Bills-Finance", "Friends-Family", "Ideas-Tech", "News"]


class EmailClassification(BaseModel):
    """Structured output from the LLM classifier."""

    category: Optional[Category] = None
    urgent: bool = False
    reason: str = ""


class ProcessedEmail(BaseModel):
    """A fully classified email record, ready for DB storage."""

    message_id: str
    sender: str
    subject: str
    snippet: str
    category: Optional[Category]
    urgent: bool
    llm_reason: str
