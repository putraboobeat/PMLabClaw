"""
core/agent.py
=============
The main agent loop.
Manages per-user conversation history, invokes the LLM, and
orchestrates the tool call → execute → respond cycle.

This is the "brain" of PmlabClaw. The Telegram polling loop lives
in main.py; this module handles everything that happens per-message.
"""

import json
import traceback
import urllib.parse
from core.config import cfg
from core.llm import LLMClient
from core.dispatcher import Dispatcher
from core.approval import approval_system
from core.gateway import BaseGateway


class Agent:
    """
    Stateful AI agent for a single Telegram channel.

    Attributes:
        history:    Sliding-window conversation history (without system prompt).
        llm:        LLM API client.
        gateway:    Default messaging gateway.
        dispatcher: Plugin dispatcher.
    """

    def __init__(self, default_gateway: BaseGateway, dispatcher: Dispatcher):
        self.llm = LLMClient()
        self.gateway = default_gateway
        self.dispatcher = dispatcher
        self.history: list[dict] = []

    # ---- Public Interface ----

    def handle_message(self, chat_id: int | str, text: str, gateway: BaseGateway = None) -> None:
        """
        Process a single incoming message end-to-end.
        Routes slash commands first, then passes to the LLM.
        """
        if gateway:
            self.gateway = gateway
        
        text = text.strip()

        # Built-in slash commands (no LLM call needed — zero tokens)
        if text == "/start":
            self._send(chat_id,
                f"⚡ *{cfg.BOT_NAME} v{cfg.VERSION}* — Active\n"
                f"Model: `{cfg.MODEL_NAME}`\n\n"
                f"I can control your VPS, schedule tasks, and more.\n"
                f"Type `/help` to see all capabilities."
            )
            self._reset_history()
            return

        if text == "/clear":
            self._reset_history()
            self._send(chat_id, "🧹 Memory cleared. Starting fresh.")
            return

        if text == "/status":
            # Shortcut: directly call system status tool
            self.history.append({"role": "user", "content": "get_system_status"})
            self._run_tool_directly(chat_id, "get_system_status", {})
            return

        if text == "/help":
            summary = self.dispatcher.get_plugin_summary()
            self._send(chat_id,
                f"⚡ *{cfg.BOT_NAME}* — Active Plugins & Tools\n\n{summary}\n\n"
                f"Just type naturally — e.g. *'cek RAM saya'* or *'restart nginx'*"
            )
            return

        if text.startswith("/approve"):
            parts = text.split()
            if len(parts) > 1:
                req_id = parts[1]
                data = approval_system.resolve(req_id, approved=True)
                if data:
                    self._send(chat_id, f"✅ Request `{req_id}` approved. Executing...")
                    # Immediately execute the tool
                    self.history.append({"role": "user", "content": f"Execute approved tool {data['tool_name']}"})
                    self._run_tool_directly(chat_id, data['tool_name'], data['args'])
                else:
                    self._send(chat_id, f"❌ Invalid or expired request ID: `{req_id}`")
            return

        if text.startswith("/deny"):
            parts = text.split()
            if len(parts) > 1:
                req_id = parts[1]
                approval_system.resolve(req_id, approved=False)
                self._send(chat_id, f"🚫 Request `{req_id}` denied.")
            return

        # Normal conversational message → LLM agent loop
        self.history.append({"role": "user", "content": text})
        self._trim_history()
        self.gateway.send_action(chat_id, "typing")
        self._agent_loop(chat_id)

    # ---- Agent Loop ----

    def _agent_loop(self, chat_id: int | str) -> None:
        """
        Runs the ReAct loop: Think → Act (tool call) → Observe → repeat.
        Stops when the LLM returns a final text answer or hits max iterations.
        """
        tools = self.dispatcher.get_all_tools()

        for iteration in range(cfg.MAX_TOOL_ITERATIONS):
            try:
                message = self.llm.chat(self.history, tools)
            except RuntimeError as e:
                self._send(chat_id, f"❌ LLM Error: {e}")
                return

            tool_calls = message.get("tool_calls")

            # ── Branch A: LLM wants to call one or more tools ──
            if tool_calls:
                # Append assistant's intent to history
                history_entry = {"role": "assistant", "tool_calls": tool_calls}
                if message.get("content"):
                    history_entry["content"] = message["content"]
                self.history.append(history_entry)

                # Execute each tool call and collect results
                for tc in tool_calls:
                    tc_id = tc.get("id", "")
                    fn_name = tc.get("function", {}).get("name", "")
                    fn_args_str = tc.get("function", {}).get("arguments", "{}")

                    # Llama 3 often hallucinates markdown blocks inside the JSON string
                    if isinstance(fn_args_str, str):
                        import re
                        fn_args_str = re.sub(r"^```(?:json)?|```$", "", fn_args_str.strip(), flags=re.MULTILINE).strip()

                    # ── CURL INTERCEPTION ──
                    # If the LLM tries to use run_command with curl for web search,
                    # redirect to the proper search_web or read_webpage tool
                    if fn_name == "run_command":
                        try:
                            cmd_args = json.loads(fn_args_str)
                            cmd = cmd_args.get("command", "")
                            if "curl" in cmd.lower():
                                import re as _re
                                # Extract URL from curl command
                                url_match = _re.search(r'https?://[^\s"\']+', cmd)
                                if url_match:
                                    curl_url = url_match.group(0)
                                    # If it's a search engine URL, redirect to search_web
                                    if any(s in curl_url.lower() for s in ["google.com/search", "duckduckgo.com", "bing.com/search"]):
                                        q_match = _re.search(r'[?&]q=([^&]+)', curl_url)
                                        query = urllib.parse.unquote_plus(q_match.group(1)) if q_match else ""
                                        if query:
                                            fn_name = "search_web"
                                            fn_args_str = json.dumps({"queries": [query]})
                                            tc["function"]["name"] = fn_name
                                            tc["function"]["arguments"] = fn_args_str
                                    else:
                                        # Non-search URL — redirect to read_webpage
                                        fn_name = "read_webpage"
                                        fn_args_str = json.dumps({"url": curl_url})
                                        tc["function"]["name"] = fn_name
                                        tc["function"]["arguments"] = fn_args_str
                        except Exception:
                            pass

                    # Intercept if approval is required
                    if self.dispatcher.requires_approval(fn_name):
                        try:
                            fn_args = json.loads(fn_args_str)
                        except Exception:
                            fn_args = {}
                        req_id = approval_system.request_approval(chat_id, fn_name, fn_args)
                        msg = (
                            f"⚠️ *Approval Required*\n"
                            f"Tool: `{fn_name}`\n"
                            f"Args: `{fn_args_str}`\n\n"
                            f"Type `/approve {req_id}` to proceed, or `/deny {req_id}` to cancel."
                        )
                        self._send(chat_id, msg)
                        
                        self.history.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": fn_name,
                            "content": f"[Pending Approval: Request ID {req_id}]"
                        })
                        continue

                    # Show the user what tool is being used
                    if fn_name == "run_command":
                        try:
                            cmd = json.loads(fn_args_str).get("command", "")
                            self._send(chat_id, f"⚡ `{cmd}`")
                        except Exception:
                            pass
                    elif fn_name == "run_script":
                        self._send(chat_id, "⚡ *Running script...*")
                    elif fn_name == "search_web":
                        try:
                            args = json.loads(fn_args_str)
                            qs = args.get("queries", [args.get("query", "")])
                            self._send(chat_id, f"🔍 *Searching: {', '.join(qs[:3])}...*")
                        except Exception:
                            self._send(chat_id, "🔍 *Searching...*")
                    elif fn_name == "read_webpage":
                        try:
                            url = json.loads(fn_args_str).get("url", "")
                            short = url[:60] + "..." if len(url) > 60 else url
                            self._send(chat_id, f"📄 *Reading: {short}*")
                        except Exception:
                            self._send(chat_id, "📄 *Reading webpage...*")

                    self.gateway.send_action(chat_id, "typing")
                    result = self.dispatcher.execute(fn_name, fn_args_str)

                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": fn_name,
                        "content": result
                    })

                self._trim_history()
                continue  # Loop back for LLM to process tool results

            # ── Branch B: LLM gives a final text answer ──
            else:
                final = message.get("content", "").strip()
                if final:
                    self.history.append({"role": "assistant", "content": final})
                    self._trim_history()
                    self._send(chat_id, final)
                else:
                    self._send(chat_id, "[Empty response from LLM]")
                return

        # If we exhausted iterations without a final answer
        self._send(chat_id, "⚠️ Max iterations reached. Task may be incomplete.")

    def _run_tool_directly(self, chat_id, tool_name: str, args: dict) -> None:
        """Bypass LLM and run a tool directly (for instant /status, etc.)"""
        import json
        result = self.dispatcher.execute(tool_name, json.dumps(args))
        self._send(chat_id, result)

    # ---- Helpers ----

    def _send(self, chat_id, text: str) -> None:
        self.gateway.send_message(chat_id, text)

    def _reset_history(self) -> None:
        self.history = []

    def _trim_history(self) -> None:
        """Keep history within token budget by sliding the window."""
        max_len = cfg.MAX_HISTORY_LENGTH
        if len(self.history) > max_len:
            # Always keep the first user message for context anchoring
            self.history = self.history[-max_len:]
