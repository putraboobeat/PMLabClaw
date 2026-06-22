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
from core.config import cfg
from core.llm import LLMClient
from core.telegram import TelegramClient
from core.dispatcher import Dispatcher


class Agent:
    """
    Stateful AI agent for a single Telegram channel.

    Attributes:
        history:    Sliding-window conversation history (without system prompt).
        llm:        LLM API client.
        telegram:   Telegram API client.
        dispatcher: Plugin dispatcher.
    """

    def __init__(self, telegram: TelegramClient, dispatcher: Dispatcher):
        self.llm = LLMClient()
        self.telegram = telegram
        self.dispatcher = dispatcher
        self.history: list[dict] = []

    # ---- Public Interface ----

    def handle_message(self, chat_id: int | str, text: str) -> None:
        """
        Process a single incoming Telegram message end-to-end.
        Routes slash commands first, then passes to the LLM.
        """
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

        # Normal conversational message → LLM agent loop
        self.history.append({"role": "user", "content": text})
        self._trim_history()
        self.telegram.send_action(chat_id, "typing")
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
                    fn_args = tc.get("function", {}).get("arguments", "{}")

                    # Show the user what command is being run
                    if fn_name == "run_command":
                        try:
                            cmd = json.loads(fn_args).get("command", "")
                            self._send(chat_id, f"⚡ `{cmd}`")
                        except Exception:
                            pass
                    elif fn_name == "run_script":
                        self._send(chat_id, "⚡ *Running script...*")

                    self.telegram.send_action(chat_id, "typing")
                    result = self.dispatcher.execute(fn_name, fn_args)

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
        self.telegram.send_message(chat_id, text)

    def _reset_history(self) -> None:
        self.history = []

    def _trim_history(self) -> None:
        """Keep history within token budget by sliding the window."""
        max_len = cfg.MAX_HISTORY_LENGTH
        if len(self.history) > max_len:
            # Always keep the first user message for context anchoring
            self.history = self.history[-max_len:]
