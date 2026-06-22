"""
core/llm.py
===========
LLM API client (OpenAI-compatible: AgentRouter, OpenAI, DeepSeek, etc.)
Handles request construction, tool/function calling format, and error handling.
Zero dependencies — uses urllib only.
"""

import json
import urllib.request
import urllib.error
from core.config import cfg


# ============================================================
# SYSTEM PROMPT — Padatkan semaksimal mungkin untuk hemat token
# ============================================================
SYSTEM_PROMPT = (
    f"You are {cfg.BOT_NAME}, a private root VPS AI agent. "
    "Execute tasks via tools. Be concise. Reply in the same language as the user. ID."
)


class LLMClient:
    """Client for any OpenAI-compatible LLM API."""

    def __init__(self):
        self.endpoint = f"{cfg.API_BASE_URL}/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.API_KEY}",
        }

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """
        Send a chat completion request.

        Args:
            messages: Conversation history (without system prompt — it's injected here).
            tools:    List of tool definitions in OpenAI function-calling format.

        Returns:
            The raw 'choices[0].message' dict from the API response.

        Raises:
            RuntimeError: On non-recoverable API errors.
        """
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        payload: dict = {
            "model": cfg.MODEL_NAME,
            "messages": full_messages,
        }
        if tools:
            payload["tools"] = tools

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=data, headers=self.headers, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                choices = body.get("choices", [])
                if not choices:
                    raise RuntimeError("LLM returned empty choices.")
                return choices[0].get("message", {})

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LLM HTTP {e.code}: {err_body[:300]}")

        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}")
