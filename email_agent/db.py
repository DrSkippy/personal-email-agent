"""PostgreSQL storage for processed email classifications."""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from email_agent.models import ProcessedEmail

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS processed_emails (
    message_id      VARCHAR(255) PRIMARY KEY,
    classified_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    category        VARCHAR(50),
    urgent          BOOLEAN      NOT NULL DEFAULT FALSE,
    sender          TEXT         NOT NULL,
    subject         TEXT         NOT NULL,
    snippet         TEXT         NOT NULL DEFAULT '',
    llm_reason      TEXT         NOT NULL DEFAULT ''
);
"""


class EmailDatabase:
    """Manages the processed_emails table in PostgreSQL."""

    def __init__(self, config: dict[str, Any]) -> None:
        db = config["database"]
        self._conn_params = {
            "host": db["host"],
            "port": db["port"],
            "user": db["user"],
            "password": os.environ["POSTGRES_PASSWORD"],
            "dbname": db["dbname"],
        }

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(**self._conn_params)

    def create_tables(self) -> None:
        """Idempotent: create the processed_emails table if it doesn't exist."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE_SQL)
            conn.commit()
        logger.info("Database tables verified")

    def is_processed(self, message_id: str) -> bool:
        """Return True if this message has already been classified."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM processed_emails WHERE message_id = %s",
                    (message_id,),
                )
                return cur.fetchone() is not None

    def save(self, email: ProcessedEmail) -> None:
        """Insert a classification record. Silently ignores duplicate message IDs."""
        sql = """
            INSERT INTO processed_emails
                (message_id, classified_at, category, urgent, sender, subject, snippet, llm_reason)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (message_id) DO NOTHING
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        email.message_id,
                        datetime.now(timezone.utc),
                        email.category,
                        email.urgent,
                        email.sender,
                        email.subject,
                        email.snippet,
                        email.llm_reason,
                    ),
                )
            conn.commit()

    def get_attention_items(self, lookback_hours: int = 1) -> list[dict[str, Any]]:
        """
        Return emails from the last N hours that need the user's attention:
        - Bills-Finance (urgent=true)
        - Friends-Family (any)
        Ordered by classified_at descending.
        """
        sql = """
            SELECT message_id, sender, subject, category, urgent, classified_at
            FROM processed_emails
            WHERE classified_at >= NOW() - (%s * INTERVAL '1 hour')
              AND (
                    (category = 'Bills-Finance' AND urgent = TRUE)
                 OR  category = 'Friends-Family'
              )
            ORDER BY classified_at DESC
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (lookback_hours,))
                return [dict(row) for row in cur.fetchall()]
