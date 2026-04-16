"""Gmail API wrapper: fetch, label, and prioritize messages."""

import base64
import logging
import os
import re
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient:
    """Thin wrapper around the Gmail API v1."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._user_id: str = config["gmail"]["user_id"]
        self._max_results: int = config["gmail"]["max_results"]
        token_path = Path(config["gmail"]["token_path"]).expanduser()
        credentials_path = Path(config["gmail"]["credentials_path"]).expanduser()
        creds = self._load_credentials(token_path, credentials_path)
        self._service = build("gmail", "v1", credentials=creds)
        self._label_cache: dict[str, str] = {}  # name → label_id

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def _load_credentials(self, token_path: Path, credentials_path: Path) -> Credentials:
        """Load or refresh OAuth credentials, running the auth flow if needed."""
        creds: Credentials | None = None

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not credentials_path.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {credentials_path}. "
                        "Download it from your Google Cloud project and place it there, "
                        "then run bin/auth_gmail.py."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())
            token_path.chmod(0o600)

        return creds  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def get_unread_inbox_messages(self) -> list[dict[str, Any]]:
        """Return unread INBOX message summaries (id + threadId)."""
        try:
            result = (
                self._service.users()
                .messages()
                .list(
                    userId=self._user_id,
                    labelIds=["INBOX", "UNREAD"],
                    maxResults=self._max_results,
                )
                .execute()
            )
            return result.get("messages", [])  # type: ignore[return-value]
        except HttpError:
            logger.exception("Failed to list unread messages")
            return []

    def get_message_details(self, message_id: str) -> dict[str, Any] | None:
        """Fetch sender, subject, snippet, and reply metadata for a single message."""
        try:
            msg = (
                self._service.users()
                .messages()
                .get(
                    userId=self._user_id,
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Message-ID", "References"],
                )
                .execute()
            )
            headers: list[dict[str, str]] = msg.get("payload", {}).get("headers", [])
            header_map = {h["name"]: h["value"] for h in headers}
            return {
                "message_id": message_id,
                "thread_id": msg.get("threadId", ""),
                "sender": header_map.get("From", ""),
                "subject": header_map.get("Subject", "(no subject)"),
                "snippet": msg.get("snippet", ""),
                "message_id_header": header_map.get("Message-ID", ""),
                "references": header_map.get("References", ""),
            }
        except HttpError:
            logger.exception("Failed to get message details for %s", message_id)
            return None

    def get_message_body(self, message_id: str) -> str:
        """Fetch the plain-text body of a message."""
        try:
            msg = (
                self._service.users()
                .messages()
                .get(userId=self._user_id, id=message_id, format="full")
                .execute()
            )
            return self._extract_text(msg.get("payload", {}))
        except HttpError:
            logger.exception("Failed to get body for message %s", message_id)
            return ""

    @staticmethod
    def _decode_body_data(data: str) -> str:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    @classmethod
    def _extract_text(cls, payload: dict[str, Any]) -> str:
        """Recursively extract plain text from a MIME payload, preferring text/plain."""
        mime_type: str = payload.get("mimeType", "")
        body_data: str = payload.get("body", {}).get("data", "")

        if mime_type == "text/plain" and body_data:
            return cls._decode_body_data(body_data)

        parts: list[dict[str, Any]] = payload.get("parts", [])
        if parts:
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    text = cls._extract_text(part)
                    if text:
                        return text
            for part in parts:
                text = cls._extract_text(part)
                if text:
                    return text

        if mime_type == "text/html" and body_data:
            return re.sub(r"<[^>]+>", " ", cls._decode_body_data(body_data))

        return ""

    def get_labeled_unread_messages(self, label_name: str) -> list[dict[str, Any]]:
        """Return unread messages carrying a specific label."""
        label_id = self._get_or_create_label(label_name)
        try:
            result = (
                self._service.users()
                .messages()
                .list(
                    userId=self._user_id,
                    labelIds=["UNREAD", label_id],
                    maxResults=self._max_results,
                )
                .execute()
            )
            return result.get("messages", [])
        except HttpError:
            logger.exception("Failed to list messages with label %r", label_name)
            return []

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
        in_reply_to: str = "",
        references: str = "",
    ) -> str:
        """Create a draft reply in Gmail and return the draft ID."""
        reply_subject = subject if re.match(r"re:", subject, re.IGNORECASE) else f"Re: {subject}"
        msg = MIMEText(body, "plain", "utf-8")
        msg["To"] = to
        msg["Subject"] = reply_subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = f"{references} {in_reply_to}".strip()
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        try:
            draft = (
                self._service.users()
                .drafts()
                .create(
                    userId=self._user_id,
                    body={"message": {"raw": raw, "threadId": thread_id}},
                )
                .execute()
            )
            return draft["id"]  # type: ignore[return-value]
        except HttpError:
            logger.exception("Failed to create draft for thread %s", thread_id)
            raise

    def swap_label(self, message_id: str, remove_name: str, add_name: str) -> None:
        """Remove one label and add another in a single API call."""
        remove_id = self._get_or_create_label(remove_name)
        add_id = self._get_or_create_label(add_name)
        try:
            self._service.users().messages().modify(
                userId=self._user_id,
                id=message_id,
                body={"addLabelIds": [add_id], "removeLabelIds": [remove_id]},
            ).execute()
        except HttpError:
            logger.exception(
                "Failed to swap label %r → %r on message %s",
                remove_name,
                add_name,
                message_id,
            )

    def apply_label(self, message_id: str, label_name: str) -> None:
        """Apply a named label to a message, creating the label if needed."""
        label_id = self._get_or_create_label(label_name)
        try:
            self._service.users().messages().modify(
                userId=self._user_id,
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
        except HttpError:
            logger.exception("Failed to apply label %r to message %s", label_name, message_id)

    def mark_important(self, message_id: str) -> None:
        """Mark a message as important."""
        try:
            self._service.users().messages().modify(
                userId=self._user_id,
                id=message_id,
                body={"addLabelIds": ["IMPORTANT"]},
            ).execute()
        except HttpError:
            logger.exception("Failed to mark message %s as important", message_id)

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def _find_in_cache(self, label_name: str) -> str | None:
        """Case-insensitive cache lookup. Returns label ID or None."""
        lower = label_name.lower()
        for name, lid in self._label_cache.items():
            if name.lower() == lower:
                return lid
        return None

    def _get_or_create_label(self, label_name: str) -> str:
        """Return the label ID for label_name, creating it if it doesn't exist.

        Matching is case-insensitive: if Gmail already has 'BILLS-FINANCE',
        looking up 'Bills-Finance' will return its ID without creating a duplicate.
        """
        # Check cache (case-insensitive)
        cache_hit = self._find_in_cache(label_name)
        if cache_hit:
            return cache_hit

        # Refresh cache from Gmail
        try:
            result = self._service.users().labels().list(userId=self._user_id).execute()
            for lbl in result.get("labels", []):
                self._label_cache[lbl["name"]] = lbl["id"]
        except HttpError:
            logger.exception("Failed to list labels")

        cache_hit = self._find_in_cache(label_name)
        if cache_hit:
            return cache_hit

        # Create label
        try:
            created = (
                self._service.users()
                .labels()
                .create(
                    userId=self._user_id,
                    body={
                        "name": label_name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                )
                .execute()
            )
            label_id: str = created["id"]
            self._label_cache[label_name] = label_id
            logger.info("Created Gmail label %r (id=%s)", label_name, label_id)
            return label_id
        except HttpError:
            logger.exception("Failed to create label %r", label_name)
            raise

    def ensure_labels_exist(self, label_names: list[str]) -> None:
        """Pre-create all agent labels. Safe to call multiple times."""
        for name in label_names:
            self._get_or_create_label(name)
            logger.info("Label ready: %r", name)
