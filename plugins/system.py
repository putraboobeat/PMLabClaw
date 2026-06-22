"""
plugins/system.py
=================
[BUILT-IN] Server system monitoring plugin.
Provides real-time stats: CPU, RAM, disk, network, processes, uptime.
Uses /proc filesystem — works on any Linux. No extra tools required.
"""

import os
import subprocess
from plugins.base import PluginBase


class SystemPlugin(PluginBase):
    """Monitor VPS system resources without external tools."""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_system_status",
                    "description": (
                        "Get a full server health report: CPU load, RAM usage, "
                        "disk usage, uptime, and top processes. "
                        "Call this when asked about server performance or health."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_services",
                    "description": "List all active/failed systemd services on the server.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filter": {
                                "type": "string",
                                "description": "Optional filter keyword (e.g. 'failed', 'nginx', 'active'). Leave empty for all."
                            }
                        }
                    }
                }
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "get_system_status":
            return self._get_status()
        elif tool_name == "list_services":
            return self._list_services(args.get("filter", ""))
        return None

    def _get_status(self) -> str:
        lines = ["⚡ *PmlabClaw — Server Status*\n"]

        # Uptime
        try:
            with open("/proc/uptime") as f:
                secs = float(f.read().split()[0])
            d, r = divmod(int(secs), 86400)
            h, m = divmod(r, 3600)
            lines.append(f"🕐 *Uptime:* {d}d {h}h {m // 60}m")
        except Exception:
            pass

        # CPU Load
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()
            lines.append(f"⚙️ *CPU Load:* {parts[0]} (1m) / {parts[1]} (5m) / {parts[2]} (15m)")
        except Exception:
            pass

        # RAM
        try:
            mem = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    mem[k.strip()] = int(v.strip().split()[0])
            total = mem.get("MemTotal", 0)
            avail = mem.get("MemAvailable", 0)
            used = total - avail
            pct = (used / total * 100) if total > 0 else 0
            lines.append(
                f"🧠 *RAM:* {used // 1024}MB used / {total // 1024}MB total ({pct:.1f}%)"
            )
            swap_total = mem.get("SwapTotal", 0)
            swap_free = mem.get("SwapFree", 0)
            swap_used = swap_total - swap_free
            if swap_total > 0:
                lines.append(
                    f"💾 *Swap:* {swap_used // 1024}MB / {swap_total // 1024}MB"
                )
        except Exception:
            pass

        # Disk
        try:
            res = subprocess.run(
                "df -h / --output=size,used,avail,pcent",
                shell=True, capture_output=True, text=True, timeout=5
            )
            disk_lines = res.stdout.strip().split("\n")
            if len(disk_lines) > 1:
                size, used, avail, pct = disk_lines[1].split()
                lines.append(f"💿 *Disk (/):* {used}/{size} used ({pct} full, {avail} free)")
        except Exception:
            pass

        # Top 5 Processes by CPU
        try:
            res = subprocess.run(
                "ps aux --sort=-%cpu | awk 'NR<=6{printf \"%-20s %5s%% %5sMB\\n\",$11,$3,int($6/1024)}'",
                shell=True, capture_output=True, text=True, timeout=5
            )
            if res.stdout.strip():
                lines.append(f"\n📊 *Top Processes (CPU):*\n```\n{res.stdout.strip()}\n```")
        except Exception:
            pass

        return "\n".join(lines)

    def _list_services(self, filter_kw: str) -> str:
        cmd = "systemctl list-units --type=service --no-pager --no-legend"
        if filter_kw in ("failed", "active", "inactive"):
            cmd += f" --state={filter_kw}"

        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            output = res.stdout.strip()
            if filter_kw and filter_kw not in ("failed", "active", "inactive"):
                output = "\n".join(
                    l for l in output.splitlines() if filter_kw.lower() in l.lower()
                )
            return f"```\n{output or 'No matching services.'}\n```"
        except Exception as e:
            return f"[Error] {e}"
