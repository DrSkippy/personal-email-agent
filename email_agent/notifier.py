"""Desktop notification digest via notify-send."""

import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class DigestNotifier:
    """Builds and sends an hourly attention digest via notify-send."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._timeout_ms: int = config["digest"]["notify_timeout_ms"]

    def send(self, items: list[dict[str, Any]]) -> None:
        """Format and dispatch a notify-send notification. No-ops if items is empty."""
        if not items:
            logger.info("No attention items for digest — skipping notification")
            return

        title, body = self._format(items)
        self._notify(title, body)

    def _format(self, items: list[dict[str, Any]]) -> tuple[str, str]:
        bills = [i for i in items if i["category"] == "Bills-Finance"]
        friends = [i for i in items if i["category"] == "Friends-Family"]

        lines: list[str] = []
        if bills:
            lines.append(f"Bills-Finance ({len(bills)} urgent):")
            for item in bills:
                sender = item["sender"].split("<")[0].strip().rstrip(",") or item["sender"]
                lines.append(f"  • {sender}: {item['subject']}")

        if friends:
            lines.append(f"Friends-Family ({len(friends)}):")
            for item in friends:
                sender = item["sender"].split("<")[0].strip().rstrip(",") or item["sender"]
                lines.append(f"  • {sender}: {item['subject']}")

        total = len(items)
        title = f"Email Agent — {total} item{'s' if total != 1 else ''} need attention"
        body = "\n".join(lines)
        return title, body

    def _notify(self, title: str, body: str) -> None:
        cmd = [
            "notify-send",
            "--urgency=normal",
            f"--expire-time={self._timeout_ms}",
            title,
            body,
        ]
        try:
            subprocess.run(cmd, check=True)
            logger.info("Digest sent: %s", title)
        except FileNotFoundError:
            logger.error("notify-send not found — is libnotify-bin installed?")
        except subprocess.CalledProcessError:
            logger.exception("notify-send failed")
