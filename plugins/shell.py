"""
plugins/shell.py
================
[BUILT-IN] Shell command execution plugin.
Allows the LLM to run any shell command on the VPS.
Includes timeout protection and clean output formatting.
"""

import subprocess
from plugins.base import PluginBase
from core.config import cfg


class ShellPlugin(PluginBase):
    """Execute shell commands on the VPS."""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": (
                        "Execute a shell command on the VPS as root. "
                        "Use for file ops, service control, installs, monitoring, etc. "
                        "For long-running tasks, suffix with '&' to background."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The exact bash command to execute."
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_script",
                    "description": (
                        "Write a multi-line bash script to a temp file and execute it. "
                        "Use this for complex multi-step operations."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "script": {
                                "type": "string",
                                "description": "The full bash script content to execute."
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Execution timeout in seconds. Default is 60."
                            }
                        },
                        "required": ["script"]
                    }
                }
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "run_command":
            return self._run_command(args.get("command", ""), cfg.SHELL_TIMEOUT)
        elif tool_name == "run_script":
            return self._run_script(
                args.get("script", ""),
                args.get("timeout", 60)
            )
        return None

    def _run_command(self, command: str, timeout: int) -> str:
        if not command.strip():
            return "[Error] Empty command."
        try:
            res = subprocess.run(
                command, shell=True, text=True,
                capture_output=True, timeout=timeout
            )
            parts = []
            if res.stdout.strip():
                parts.append(f"```\n{res.stdout.strip()}\n```")
            if res.stderr.strip():
                parts.append(f"*stderr:*\n```\n{res.stderr.strip()}\n```")
            if res.returncode != 0:
                parts.append(f"*Exit code: {res.returncode}*")
            return "\n".join(parts) if parts else "✅ Done (no output)"
        except subprocess.TimeoutExpired:
            return f"[Error] Command timed out after {timeout}s."
        except Exception as e:
            return f"[Error] {e}"

    def _run_script(self, script: str, timeout: int) -> str:
        import tempfile, os
        if not script.strip():
            return "[Error] Empty script."
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False, prefix="/tmp/pmlabclaw_"
            ) as f:
                f.write("#!/bin/bash\nset -e\n" + script)
                tmp_path = f.name
            os.chmod(tmp_path, 0o700)
            result = self._run_command(f"bash {tmp_path}", timeout)
            os.unlink(tmp_path)
            return result
        except Exception as e:
            return f"[Error] Script execution failed: {e}"
