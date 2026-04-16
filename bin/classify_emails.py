#!/usr/bin/env python3
"""Classify unread Gmail messages and apply labels.

Run every 10 minutes via cron:
    */10 * * * * cd /home/scott/Working/personal-email-agent && \
        poetry run python bin/classify_emails.py >> /var/log/email-agent.log 2>&1

Requires: PYTHONPATH set to project root, or run via poetry.
"""

import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from email_agent.classifier import EmailClassifier
from email_agent.db import EmailDatabase
from email_agent.gmail_client import GmailClient
from email_agent.models import ProcessedEmail

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("classify_emails")

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

CATEGORY_TO_LABEL_KEY = {
    "Advertising": "advertising",
    "Bills-Finance": "bills_finance",
    "Friends-Family": "friends_family",
    "Ideas-Tech": "ideas_tech",
    "News": "news",
}


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text())

    db = EmailDatabase(config)
    db.create_tables()

    gmail = GmailClient(config)
    classifier = EmailClassifier(config)

    messages = gmail.get_unread_inbox_messages()
    if not messages:
        logger.info("No unread messages found")
        return

    logger.info("Found %d unread message(s)", len(messages))
    classified = skipped = unchanged = api_errors = 0

    for msg in messages:
        message_id: str = msg["id"]

        if db.is_processed(message_id):
            skipped += 1
            continue

        details = gmail.get_message_details(message_id)
        if not details:
            continue

        result = classifier.classify(
            sender=details["sender"],
            subject=details["subject"],
            snippet=details["snippet"],
        )

        # None means an API/infrastructure failure — skip DB save so it's retried next run
        if result is None:
            logger.warning("API error for message %s — will retry next run", message_id)
            api_errors += 1
            continue

        if result.category is not None:
            label_key = CATEGORY_TO_LABEL_KEY[result.category]
            label_name: str = config["labels"][label_key]
            gmail.apply_label(message_id, label_name)

            if result.urgent:
                gmail.mark_important(message_id)

            logger.info(
                "[%s] %s — %r (urgent=%s)",
                result.category,
                details["subject"][:60],
                details["sender"][:40],
                result.urgent,
            )
            classified += 1
        else:
            logger.info(
                "[unclassified] %s — %r",
                details["subject"][:60],
                details["sender"][:40],
            )
            unchanged += 1

        db.save(
            ProcessedEmail(
                message_id=message_id,
                sender=details["sender"],
                subject=details["subject"],
                snippet=details["snippet"],
                category=result.category,
                urgent=result.urgent,
                llm_reason=result.reason,
            )
        )

    logger.info(
        "Done — classified=%d  unchanged=%d  api_errors=%d  skipped(already processed)=%d",
        classified,
        unchanged,
        api_errors,
        skipped,
    )


if __name__ == "__main__":
    main()
