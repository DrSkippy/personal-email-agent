#!/usr/bin/env bash
set -euo pipefail

PROJ="/home/scott/Working/personal-email-agent"
cd "$PROJ"

# Load secrets (.envrc not sourced automatically in cron)
# shellcheck source=../.envrc
source "$PROJ/.envrc"

# Ensure poetry is on PATH
export PATH="/home/scott/.local/bin:$PATH"

exec poetry run python bin/classify_emails.py
