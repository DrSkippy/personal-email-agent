#!/usr/bin/env bash
set -euo pipefail

PROJ="/home/scott/Working/personal-email-agent"
cd "$PROJ"

# Load secrets (.envrc not sourced automatically in cron)
# shellcheck source=../.envrc
source "$PROJ/.envrc"

# Ensure poetry is on PATH
export PATH="/home/scott/.local/bin:$PATH"

# DISPLAY and DBUS are required for notify-send from a cron context
export DISPLAY="${DISPLAY:-:0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/1000/bus}"

exec poetry run python bin/hourly_digest.py
