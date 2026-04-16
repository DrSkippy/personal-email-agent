#!/usr/bin/env python3
"""Send an hourly notify-send digest of emails needing attention.

Run every hour via cron:
    0 * * * * cd /home/scott/Working/personal-email-agent && \
        DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
        poetry run python bin/hourly_digest.py >> /var/log/email-agent-digest.log 2>&1

Sends a desktop notification summarising:
  - Bills-Finance emails marked urgent
  - Friends-Family emails (any)
from the past hour.
"""

import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from email_agent.db import EmailDatabase
from email_agent.notifier import DigestNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hourly_digest")

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text())

    db = EmailDatabase(config)
    notifier = DigestNotifier(config)

    lookback = config["digest"]["lookback_hours"]
    items = db.get_attention_items(lookback_hours=lookback)

    logger.info("Attention items in the last %d hour(s): %d", lookback, len(items))
    notifier.send(items)


if __name__ == "__main__":
    main()
