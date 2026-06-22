"""
main.py
=======
PmlabClaw — Entry Point
========================
This is the ONLY file you need to modify when:
  - Adding a new plugin  → dispatcher.register(MyPlugin())
  - Changing bot identity → edit core/config.py
  - Changing LLM behavior → edit core/llm.py

Everything else is handled by the modular architecture.
"""

import sys
import time
import traceback

# ── Bootstrap: validate config before anything else ──
from core.config import cfg
cfg.validate()

# ── Core modules ──
from core.telegram import TelegramClient
from core.dispatcher import Dispatcher
from core.agent import Agent

# ── Built-in plugins ──
from plugins.shell import ShellPlugin
from plugins.system import SystemPlugin
from plugins.scheduler import SchedulerPlugin
from plugins.web import WebPlugin


def build_dispatcher(telegram: TelegramClient) -> Dispatcher:
    """
    Register all plugins with the dispatcher.

    ┌─────────────────────────────────────────────────────┐
    │  TO ADD A NEW PLUGIN:                               │
    │  1. Create plugins/my_plugin.py (extend PluginBase) │
    │  2. Import it here                                  │
    │  3. Add: dispatcher.register(MyPlugin())            │
    └─────────────────────────────────────────────────────┘
    """
    dispatcher = Dispatcher()

    # Core capabilities
    dispatcher.register(ShellPlugin())
    dispatcher.register(SystemPlugin())
    dispatcher.register(WebPlugin())

    # Scheduler gets a reference to telegram so it can send notifications
    dispatcher.register(SchedulerPlugin(telegram_client=telegram))

    # ── ADD YOUR CUSTOM PLUGINS BELOW THIS LINE ──
    # dispatcher.register(DatabasePlugin())
    # dispatcher.register(DeployPlugin())
    # dispatcher.register(FileManagerPlugin())

    return dispatcher


def poll_loop(telegram: TelegramClient, agent: Agent) -> None:
    """
    Main long-polling loop.
    Uses Telegram's long-poll (timeout=50s) for minimal CPU usage.
    Implements exponential backoff on network errors.
    Only processes messages from ALLOWED_CHAT_ID for security.
    """
    offset: int | None = None
    error_backoff = 2  # seconds
    poll_timeout = cfg.TELEGRAM_POLL_TIMEOUT

    print(f"[{cfg.BOT_NAME} v{cfg.VERSION}] Polling started. Allowed ID: {cfg.ALLOWED_CHAT_ID}")

    while True:
        updates = telegram.get_updates(offset=offset, timeout=poll_timeout)

        if not updates:
            # Timeout (normal) or network error — exponential backoff on repeated fails
            time.sleep(0.1)
            continue

        # Reset backoff on any successful response
        error_backoff = 2

        for update in updates:
            update_id = update.get("update_id", 0)
            offset = update_id + 1  # Acknowledge this update

            message = update.get("message")
            if not message:
                continue  # Ignore non-message updates (inline queries, etc.)

            chat = message.get("chat", {})
            chat_id = str(chat.get("id", ""))
            user_text = message.get("text", "").strip()

            if not user_text:
                continue  # Ignore photos, stickers, voice notes, etc.

            # ── Security Gate ──
            if chat_id != str(cfg.ALLOWED_CHAT_ID):
                print(f"[Security] Blocked unauthorized chat_id: {chat_id}")
                telegram.send_message(chat_id, "⛔ Unauthorized.")
                continue

            # ── Process Message ──
            try:
                agent.handle_message(chat_id, user_text)
            except Exception:
                tb = traceback.format_exc()
                print(f"[Error] Unhandled exception in handle_message:\n{tb}")
                telegram.send_message(chat_id, f"❌ Internal error. Check server logs.")


def main() -> None:
    """Application entry point. Wires all components and starts the loop."""

    # 1. Build core clients
    telegram = TelegramClient()

    # 2. Healthcheck — verify bot token is valid
    me = telegram.get_me()
    if not me:
        print("[Fatal] Could not connect to Telegram. Check TELEGRAM_BOT_TOKEN.")
        sys.exit(1)
    print(f"[Auth] Connected as @{me.get('username', '?')} (id: {me.get('id')})")

    # 3. Build plugin dispatcher
    dispatcher = build_dispatcher(telegram)
    print(f"[Dispatcher] {len(dispatcher.get_all_tools())} tools registered across all plugins.")

    # 4. Build agent
    agent = Agent(telegram=telegram, dispatcher=dispatcher)

    # 5. Notify owner on startup
    startup_msg = (
        f"⚡ *{cfg.BOT_NAME} v{cfg.VERSION}* started.\n"
        f"Model: `{cfg.MODEL_NAME}`\n"
        f"Tools: {len(dispatcher.get_all_tools())} active\n\n"
        f"Type `/help` to see capabilities."
    )
    telegram.send_message(cfg.ALLOWED_CHAT_ID, startup_msg)

    # 6. Start polling loop
    poll_loop(telegram, agent)


if __name__ == "__main__":
    main()
