"""
core/llm.py
===========
LLM API client supporting both OpenAI-compatible endpoints and native Anthropic.
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
    """Client for LLM APIs (Auto-detects Anthropic vs OpenAI format)."""

    def __init__(self):
        self.api_key = cfg.API_KEY
        self.is_anthropic = self.api_key.startswith("sk-ant-")

        if self.is_anthropic:
            self.endpoint = "https://api.anthropic.com/v1/messages"
            self.headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        else:
            self.endpoint = f"{cfg.API_BASE_URL}/chat/completions"
            self.headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """
        Send a chat completion request.
        Translates formats behind the scenes so the rest of the bot only sees OpenAI format.
        """
        if self.is_anthropic:
            return self._chat_anthropic(messages, tools)
        else:
            return self._chat_openai(messages, tools)

    def _chat_openai(self, messages: list[dict], tools: list[dict] | None) -> dict:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        payload: dict = {
            "model": cfg.MODEL_NAME,
            "messages": full_messages,
        }
        if tools:
            payload["tools"] = tools

        return self._send_request(payload, is_anthropic=False)

    def _chat_anthropic(self, messages: list[dict], tools: list[dict] | None) -> dict:
        anthropic_msgs = []
        
        i = 0
        while i < len(messages):
            msg = messages[i]
            
            if msg["role"] == "user":
                anthropic_msgs.append({"role": "user", "content": msg["content"]})
                
            elif msg["role"] == "assistant":
                content = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        content.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": json.loads(tc["function"]["arguments"])
                        })
                # Anthropic doesn't allow empty assistant messages
                if not content:
                     content.append({"type": "text", "text": "..."})
                anthropic_msgs.append({"role": "assistant", "content": content})
                
            elif msg["role"] == "tool":
                # Group consecutive tool results into one user message
                tool_results = []
                while i < len(messages) and messages[i]["role"] == "tool":
                    tm = messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tm["tool_call_id"],
                        "content": str(tm["content"])
                    })
                    i += 1
                anthropic_msgs.append({"role": "user", "content": tool_results})
                i -= 1 # Adjust loop counter
                
            i += 1

        payload: dict = {
            "model": cfg.MODEL_NAME,
            "system": SYSTEM_PROMPT,
            "messages": anthropic_msgs,
            "max_tokens": 4096
        }
        
        if tools:
            ant_tools = []
            for t in tools:
                f = t["function"]
                ant_tools.append({
                    "name": f["name"],
                    "description": f.get("description", ""),
                    "input_schema": f["parameters"]
                })
            payload["tools"] = ant_tools

        return self._send_request(payload, is_anthropic=True)

    def _send_request(self, payload: dict, is_anthropic: bool) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=data, headers=self.headers, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                
                if is_anthropic:
                    return self._parse_anthropic_response(body)
                else:
                    choices = body.get("choices", [])
                    if not choices:
                        raise RuntimeError("LLM returned empty choices.")
                    return choices[0].get("message", {})

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LLM HTTP {e.code}: {err_body[:300]}")
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}")

    def _parse_anthropic_response(self, response_body: dict) -> dict:
        msg = {"role": "assistant", "content": None}
        tool_calls = []
        
        for block in response_body.get("content", []):
            if block["type"] == "text":
                if msg["content"] is None:
                    msg["content"] = ""
                msg["content"] += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block["input"])
                    }
                })
                
        if tool_calls:
            msg["tool_calls"] = tool_calls
            
        return msg
