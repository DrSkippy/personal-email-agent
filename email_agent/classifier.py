"""LLM-based email classifier backed by LM Studio (OpenAI-compatible API)."""

import json
import logging
import os
import re
from typing import Any, Optional

from openai import OpenAI
from pydantic import ValidationError

from email_agent.models import EmailClassification

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """/no_think
You are an email classifier. Given an email's sender, subject, and snippet, classify it into exactly one category or return null if none clearly applies — do not guess.

Categories:
- Advertising: Marketing or promotional emails from subscribed vendors. Always urgent=false. No response needed.
- Bills-Finance: Credit card statements, bank statements, investment account notices, utility bills, or any bill requiring payment or action. Mark urgent=true only when a payment due date or immediate action is explicitly mentioned.
- Friends-Family: Personal emails from people the user knows personally. Always urgent=false.
- Ideas-Tech: Informational emails about AI, programming, data science, machine learning, coffee equipment (reviews or comparisons, not sales), fountain pens, or notebooks. Must be informational content — not promotional or sales. Always urgent=false.
- News: News digests, newsletters, and current events emails from news outlets, journalists, or editorial publications (e.g. Axios, Substack writers, newsletters). Always urgent=false. Distinct from Advertising — News informs, Advertising sells.

If the email does not clearly fit one of these five categories, return null for category.

Respond ONLY with valid JSON — no markdown, no explanation outside the JSON object:
{"category": "Advertising"|"Bills-Finance"|"Friends-Family"|"Ideas-Tech"|"News"|null, "urgent": true|false, "reason": "one sentence"}"""


class EmailClassifier:
    """Classifies emails using a local LM Studio model."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._client = OpenAI(
            base_url=config["lm_studio"]["base_url"],
            api_key=os.environ["LM_STUDIO_API_KEY"],
        )
        self._model: str = config["lm_studio"]["model"]
        self._temperature: float = config["lm_studio"].get("temperature", 0.1)
        self._max_tokens: int = config["lm_studio"].get("max_tokens", 1024)

    @staticmethod
    def _sanitize(value: str, max_len: int) -> str:
        """Strip control characters and enforce a length cap."""
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
        return cleaned[:max_len]

    def classify(self, sender: str, subject: str, snippet: str) -> Optional[EmailClassification]:
        """Classify a single email.

        Returns:
            EmailClassification on success (category may be None if no match).
            None on API or infrastructure failure — caller should NOT save to DB,
            so the email is retried on the next run.
        """
        safe_sender = self._sanitize(sender, 200)
        safe_subject = self._sanitize(subject, 300)
        safe_snippet = self._sanitize(snippet, 300)
        # Wrap fields in explicit delimiters so injected instructions in the
        # email content cannot be mistaken for classifier instructions.
        user_message = (
            "<email>\n"
            f"<from>{safe_sender}</from>\n"
            f"<subject>{safe_subject}</subject>\n"
            f"<snippet>{safe_snippet}</snippet>\n"
            "</email>\n"
            "Classify the email above. Output only JSON."
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            content = response.choices[0].message.content or ""
            parsed = self._parse(content)
            if parsed is None:
                # Empty response after stripping think tags — model ran out of
                # context during reasoning. Treat as infrastructure failure so
                # the email is retried next run rather than stored as unclassified.
                logger.warning(
                    "Empty model output for message from %s — will retry next run", sender
                )
                return None
            return parsed
        except Exception:
            logger.exception("LM Studio request failed for message from %s", sender)
            return None  # signals caller to skip DB save

    def _parse(self, content: str) -> Optional[EmailClassification]:
        """Strip any <think> block and parse the JSON response.

        Returns None if the content was empty after stripping (model produced
        no output, likely due to thinking budget exhaustion).
        """
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if not content:
            return None
        try:
            data = json.loads(content)
            # Model sometimes returns the string "null" instead of JSON null
            if data.get("category") == "null":
                data["category"] = None
            return EmailClassification(**data)
        except (json.JSONDecodeError, ValidationError):
            logger.warning("Could not parse classifier response: %r", content[:200])
            # Parse failure on non-empty content is treated as "no match"
            # (deliberate unclassified), so we save to DB and don't retry.
            return EmailClassification()
