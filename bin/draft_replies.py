#!/usr/bin/env python3
"""Draft replies to emails labeled REPLY-REQUIRED.

For each unread REPLY-REQUIRED email, fetches the full body, uses the LLM to
draft a reply, saves it to Gmail Drafts, and swaps the label to REPLY-DRAFTED.
Emails remain unread so they stay visible in the inbox.

Run every 10 minutes via cron:
    */10 * * * * /home/scott/Working/personal-email-agent/bin/cron_draft.sh >> /var/log/email-agent-draft.log 2>&1
"""

import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from email_agent.drafter import EmailDrafter
from email_agent.gmail_client import GmailClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("draft_replies")

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

LABEL_REQUIRED = "REPLY-REQUIRED"
LABEL_DRAFTED = "REPLY-DRAFTED"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    gmail = GmailClient(config)
    drafter = EmailDrafter(config)

    messages = gmail.get_labeled_unread_messages(LABEL_REQUIRED)
    if not messages:
        logger.info("No REPLY-REQUIRED messages found")
        return

    logger.info("Found %d REPLY-REQUIRED message(s)", len(messages))
    drafted = failed = 0

    for msg in messages:
        message_id: str = msg["id"]

        details = gmail.get_message_details(message_id)
        if not details:
            failed += 1
            continue

        body = gmail.get_message_body(message_id)

        result = drafter.draft(
            sender=details["sender"],
            subject=details["subject"],
            body=body,
        )
        if result is None:
            logger.warning("Draft failed for message %s — skipping", message_id)
            failed += 1
            continue

        try:
            draft_id = gmail.create_draft(
                to=details["sender"],
                subject=details["subject"],
                body=result.body,
                thread_id=details["thread_id"],
                in_reply_to=details["message_id_header"],
                references=details["references"],
            )
        except Exception:
            logger.exception("Could not save draft for message %s", message_id)
            failed += 1
            continue

        gmail.swap_label(message_id, LABEL_REQUIRED, LABEL_DRAFTED)
        logger.info(
            "[drafted] %s — %r (draft_id=%s)",
            details["subject"][:60],
            details["sender"][:40],
            draft_id,
        )
        drafted += 1

    logger.info("Done — drafted=%d  failed=%d", drafted, failed)


if __name__ == "__main__":
    main()
