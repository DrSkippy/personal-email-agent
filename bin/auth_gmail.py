#!/usr/bin/env python3
"""One-time interactive Gmail OAuth flow.

Run this once to generate ~/.config/email-agent/token.json.
Subsequent runs of the agent will auto-refresh the token.

Usage:
    poetry run python bin/auth_gmail.py
"""

import sys
from pathlib import Path

import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    credentials_path = Path(config["gmail"]["credentials_path"]).expanduser()
    token_path = Path(config["gmail"]["token_path"]).expanduser()

    if not credentials_path.exists():
        print(f"ERROR: credentials.json not found at {credentials_path}")
        print("Download it from your Google Cloud Console:")
        print("  APIs & Services → Credentials → OAuth 2.0 Client IDs → Download")
        sys.exit(1)

    print(f"Starting OAuth flow for Gmail...")
    print(f"A browser window will open. Log in and grant access.")

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    print(f"\nToken saved to {token_path}")
    print("You can now run the agent.")


if __name__ == "__main__":
    main()
