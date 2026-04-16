"""LLM-based reply drafter backed by LM Studio (OpenAI-compatible API)."""

import logging
import os
import re
from typing import Any, Optional

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """/no_think
You are drafting reply emails on behalf of Scott.

Rules:
- Match the tone of the incoming email: formal if formal, casual if casual
- Be concise — no filler, no pleasantries beyond what the tone requires
- Structure:
  1. One sentence recapping your understanding of the request or situation
  2. Your proposed response, answer, or action — include a concrete timeline if relevant
- If the request is complex or has multiple viable responses, draft TWO clearly separated options:

--- Option A ---
[draft]

--- Option B ---
[draft]

  Scott will delete the option he doesn't want before sending.
- Sign off with just "Scott" on its own line
- Output only the email body — no subject line, no metadata
"""


class DraftReply(BaseModel):
    """Validated reply draft from the LLM."""

    body: str


class EmailDrafter:
    """Drafts reply emails using a local LM Studio model."""

    def __init__(self, config: dict[str, Any]) -> None:
        drafter_cfg: dict[str, Any] = config.get("drafter", {})
        lm_cfg: dict[str, Any] = config["lm_studio"]
        self._client = OpenAI(
            base_url=lm_cfg["base_url"],
            api_key=os.environ["LM_STUDIO_API_KEY"],
        )
        self._model: str = drafter_cfg.get("model", lm_cfg["model"])
        self._temperature: float = drafter_cfg.get("temperature", 0.4)
        self._max_tokens: int = drafter_cfg.get("max_tokens", 800)

    def draft(self, sender: str, subject: str, body: str) -> Optional[DraftReply]:
        """Draft a reply to the given email.

        Returns DraftReply on success, None on API or infrastructure failure.
        """
        user_message = (
            "<email>\n"
            f"<from>{sender}</from>\n"
            f"<subject>{subject}</subject>\n"
            f"<body>{body[:3000]}</body>\n"
            "</email>\n"
            "Draft a reply."
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
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            if not content:
                logger.warning("Empty draft response for message from %s", sender)
                return None
            return DraftReply(body=content)
        except Exception:
            logger.exception("LM Studio draft request failed for message from %s", sender)
            return None
