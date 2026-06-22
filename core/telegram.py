"""
core/telegram.py
================
Telegram Bot API client.
Handles sending messages, chat actions, and long-polling for updates.
All calls use Python's built-in urllib — zero dependencies.
"""

import json
import urllib.request
import urllib.error
from core.config import cfg
from core.gateway import BaseGateway


class TelegramClient(BaseGateway):
    """Lightweight Telegram Bot API wrapper."""

    BASE_URL = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}"

    def _post(self, method: str, payload: dict, timeout: int = 15) -> dict:
        """Generic POST request to any Telegram Bot API method."""
        url = f"{self.BASE_URL}/{method}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            print(f"[Telegram] HTTP {e.code} on {method}: {error_body[:200]}")
            return {}
        except Exception as e:
            print(f"[Telegram] Error on {method}: {e}")
            return {}

    def send_message(self, chat_id: int | str, text: str, parse_mode: str = "Markdown") -> None:
        """Send a text message, auto-chunking if it exceeds 4096 characters."""
        max_len = 4000
        chunks = [text[i:i + max_len] for i in range(0, max(len(text), 1), max_len)]

        for chunk in chunks:
            payload = {"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode}
            result = self._post("sendMessage", payload)

            # Fallback to plain text if Markdown parse fails
            if not result.get("ok") and parse_mode != "":
                payload.pop("parse_mode", None)
                self._post("sendMessage", payload)

    def send_action(self, chat_id: int | str, action: str = "typing") -> None:
        """Show a typing/uploading indicator to the user."""
        self._post("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=5)

    def get_updates(self, offset: int | None, timeout: int) -> list[dict]:
        """
        Long-poll Telegram for new messages.
        Returns a list of Update objects. Empty list on timeout or error.
        """
        url = f"{self.BASE_URL}/getUpdates?timeout={timeout}"
        if offset is not None:
            url += f"&offset={offset}"

        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("result", [])
        except Exception:
            return []

    def get_me(self) -> dict:
        """Get basic info about the bot itself (useful for healthcheck)."""
        url = f"{self.BASE_URL}/getMe"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8")).get("result", {})
        except Exception:
            return {}
