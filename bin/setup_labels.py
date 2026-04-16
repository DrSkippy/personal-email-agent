#!/usr/bin/env python3
"""One-time Gmail label setup.

Creates all email-agent/* labels in Gmail if they don't already exist.
Safe to re-run — existing labels are left unchanged.

Usage:
    poetry run python bin/setup_labels.py
"""

import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from email_agent.gmail_client import GmailClient

logging.basicConfig(level=logging.INFO, format="%(message)s")

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    label_names = list(config["labels"].values())

    print("Setting up Gmail labels...")
    client = GmailClient(config)
    client.ensure_labels_exist(label_names)

    print("\nLabels ready:")
    for name in label_names:
        print(f"  ✓ {name}")


if __name__ == "__main__":
    main()
