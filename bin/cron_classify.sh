#!/usr/bin/env bash
set -euo pipefail

PROJ="/home/scott/Working/personal-email-agent"
cd "$PROJ"

# Load secrets (.envrc not sourced automatically in cron)
# shellcheck source=../.envrc
source "$PROJ/.envrc"

exec "$PROJ/.venv/bin/python" bin/classify_emails.py
