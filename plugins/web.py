"""
plugins/web.py
==============
[BUILT-IN] HTTP request plugin.
Allows the LLM to fetch URLs, call webhooks, or hit external APIs.
Uses urllib only — zero dependencies.
"""

import json
import urllib.request
import urllib.error
import urllib.parse
from plugins.base import PluginBase


class WebPlugin(PluginBase):
    """Fetch URLs and call HTTP endpoints."""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "http_request",
                    "description": (
                        "Make an HTTP request to any URL. "
                        "Supports GET, POST, PUT, DELETE. "
                        "Use for calling webhooks, checking APIs, or fetching web content."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The full URL to request."
                            },
                            "method": {
                                "type": "string",
                                "enum": ["GET", "POST", "PUT", "DELETE"],
                                "description": "HTTP method. Default: GET"
                            },
                            "body": {
                                "type": "string",
                                "description": "Request body as a JSON string (for POST/PUT)."
                            },
                            "headers": {
                                "type": "object",
                                "description": "Optional extra HTTP headers as key-value pairs."
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "http_request":
            return self._http_request(
                url=args.get("url", ""),
                method=args.get("method", "GET").upper(),
                body=args.get("body"),
                headers=args.get("headers", {})
            )
        return None

    def _http_request(self, url: str, method: str, body: str | None, headers: dict) -> str:
        if not url:
            return "[Error] URL is required."

        data = None
        if body:
            data = body.encode("utf-8") if isinstance(body, str) else body

        default_headers = {"User-Agent": "PmlabClaw/1.0", "Content-Type": "application/json"}
        default_headers.update(headers or {})

        req = urllib.request.Request(url, data=data, headers=default_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8", errors="ignore")

                # Pretty-print JSON if applicable
                if "json" in content_type:
                    try:
                        parsed = json.loads(raw)
                        body_str = json.dumps(parsed, indent=2, ensure_ascii=False)
                    except Exception:
                        body_str = raw
                else:
                    body_str = raw[:2000]  # Truncate large HTML

                return f"*HTTP {status}*\n```\n{body_str}\n```"

        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")[:500]
            return f"[HTTP Error {e.code}] {err}"
        except Exception as e:
            return f"[Error] {e}"
