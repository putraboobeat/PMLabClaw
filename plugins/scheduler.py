"""
plugins/scheduler.py
====================
[BUILT-IN] Task scheduler plugin.
Allows the LLM to create, list, and remove cron-like scheduled tasks
directly from Telegram chat — no manual crontab editing needed.

Tasks are stored in the tasks/ directory as simple Python files.
The scheduler runs in its own background thread inside the main process.
"""

import os
import json
import time
import threading
import importlib.util
from datetime import datetime
from plugins.base import PluginBase


# Path to the tasks directory (sibling of plugins/)
_TASKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tasks"
)
_SCHEDULE_FILE = os.path.join(_TASKS_DIR, "schedule.json")


class SchedulerPlugin(PluginBase):
    """
    Lightweight in-process task scheduler.
    Tasks are stored in tasks/schedule.json as interval-based jobs.
    A background thread ticks every 30 seconds to check for due tasks.
    """

    def __init__(self, telegram_client=None):
        """
        Args:
            telegram_client: Optional TelegramClient instance for sending
                             notifications when scheduled tasks complete.
        """
        self._telegram = telegram_client
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()
        print("[Scheduler] Background tick thread started.")

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "schedule_task",
                    "description": (
                        "Schedule a recurring task to run automatically at a fixed interval. "
                        "The task is a shell command that runs every N minutes/hours."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "A short unique name for this task (e.g. 'backup-db')."
                            },
                            "command": {
                                "type": "string",
                                "description": "The shell command to run."
                            },
                            "interval_minutes": {
                                "type": "integer",
                                "description": "How often to run this task, in minutes."
                            },
                            "notify": {
                                "type": "boolean",
                                "description": "If true, send Telegram notification with output when task runs."
                            }
                        },
                        "required": ["name", "command", "interval_minutes"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_scheduled_tasks",
                    "description": "List all currently scheduled recurring tasks.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "remove_scheduled_task",
                    "description": "Remove/cancel a scheduled task by its name.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The name of the task to remove."
                            }
                        },
                        "required": ["name"]
                    }
                }
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "schedule_task":
            return self._add_task(args)
        elif tool_name == "list_scheduled_tasks":
            return self._list_tasks()
        elif tool_name == "remove_scheduled_task":
            return self._remove_task(args.get("name", ""))
        return None

    # ---- Schedule Management ----

    def _load_schedule(self) -> dict:
        if os.path.exists(_SCHEDULE_FILE):
            try:
                with open(_SCHEDULE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_schedule(self, schedule: dict):
        os.makedirs(_TASKS_DIR, exist_ok=True)
        with open(_SCHEDULE_FILE, "w") as f:
            json.dump(schedule, f, indent=2)

    def _add_task(self, args: dict) -> str:
        name = args.get("name", "").strip().replace(" ", "-")
        command = args.get("command", "")
        interval = int(args.get("interval_minutes", 60))
        notify = bool(args.get("notify", False))

        if not name or not command:
            return "[Error] 'name' and 'command' are required."

        with self._lock:
            schedule = self._load_schedule()
            schedule[name] = {
                "command": command,
                "interval_seconds": interval * 60,
                "notify": notify,
                "last_run": 0,
                "created_at": datetime.utcnow().isoformat()
            }
            self._save_schedule(schedule)

        return (
            f"✅ Task `{name}` scheduled.\n"
            f"Command: `{command}`\n"
            f"Interval: every {interval} minute(s)\n"
            f"Notify on run: {'Yes' if notify else 'No'}"
        )

    def _list_tasks(self) -> str:
        with self._lock:
            schedule = self._load_schedule()

        if not schedule:
            return "No scheduled tasks. Use `schedule_task` to add one."

        lines = ["📅 *Scheduled Tasks:*\n"]
        for name, task in schedule.items():
            interval_m = task["interval_seconds"] // 60
            last = task.get("last_run", 0)
            last_str = datetime.utcfromtimestamp(last).strftime("%Y-%m-%d %H:%M UTC") if last else "Never"
            lines.append(
                f"• `{name}` — every {interval_m}m\n"
                f"  Cmd: `{task['command'][:50]}`\n"
                f"  Last run: {last_str}"
            )
        return "\n".join(lines)

    def _remove_task(self, name: str) -> str:
        with self._lock:
            schedule = self._load_schedule()
            if name not in schedule:
                return f"[Error] No task named `{name}` found."
            del schedule[name]
            self._save_schedule(schedule)
        return f"✅ Task `{name}` removed."

    # ---- Background Ticker ----

    def _tick_loop(self):
        """Check every 30 seconds if any task is due to run."""
        while not self._stop_event.is_set():
            self._stop_event.wait(30)
            if self._stop_event.is_set():
                break
            self._check_and_run()

    def _check_and_run(self):
        now = time.time()
        with self._lock:
            schedule = self._load_schedule()
            changed = False

            for name, task in schedule.items():
                if not isinstance(task, dict):
                    continue
                last_run = task.get("last_run", 0)
                interval = task.get("interval_seconds", 3600)

                if now - last_run >= interval:
                    task["last_run"] = now
                    changed = True
                    threading.Thread(
                        target=self._run_task,
                        args=(name, task),
                        daemon=True
                    ).start()

            if changed:
                self._save_schedule(schedule)

    def _run_task(self, name: str, task: dict):
        import subprocess
        command = task.get("command", "")
        print(f"[Scheduler] Running task: {name} -> {command}")

        try:
            res = subprocess.run(
                command, shell=True, text=True,
                capture_output=True, timeout=60
            )
            output = (res.stdout + res.stderr).strip()[:1000]
        except subprocess.TimeoutExpired:
            output = "[Timeout] Task exceeded 60s."
        except Exception as e:
            output = f"[Error] {e}"

        if task.get("notify") and self._telegram:
            from core.config import cfg
            msg = f"⏰ *Task `{name}` ran*\n```\n{output or '(no output)'}\n```"
            self._telegram.send_message(cfg.ALLOWED_CHAT_ID, msg)
