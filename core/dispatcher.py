"""
core/dispatcher.py
==================
Plugin registry and tool dispatcher.
This is the central "router" — it collects all tools from all plugins
and routes incoming tool-call requests to the correct executor.

To add a new capability: create a plugin in plugins/ and register it
in main.py. You never need to touch this file.
"""

import json
from typing import Any
from plugins.base import PluginBase


class Dispatcher:
    """
    Manages a registry of plugins and dispatches tool calls to them.

    Usage:
        dispatcher = Dispatcher()
        dispatcher.register(ShellPlugin())
        dispatcher.register(SystemPlugin())

        # Get all tools for LLM
        tools = dispatcher.get_all_tools()

        # Execute a tool call
        result = dispatcher.execute("run_command", {"command": "uptime"})
    """

    def __init__(self):
        self._plugins: list[PluginBase] = []
        self._tool_map: dict[str, PluginBase] = {}

    def clear(self) -> None:
        """Clear all registered plugins and tools (used during reload)."""
        self._plugins.clear()
        self._tool_map.clear()

    def register(self, plugin: PluginBase) -> None:
        """Register a plugin and index all its tools for fast dispatch."""
        self._plugins.append(plugin)
        for tool_def in plugin.tools:
            tool_name = tool_def.get("function", {}).get("name")
            if tool_name:
                self._tool_map[tool_name] = plugin
                print(f"[Dispatcher] Registered tool: {tool_name} ({type(plugin).__name__})")

    def get_all_tools(self) -> list[dict]:
        """Return all tool definitions from all registered plugins (for LLM)."""
        tools = []
        for plugin in self._plugins:
            tools.extend(plugin.tools)
        return tools

    def get_plugin_summary(self) -> str:
        """Return a human-readable list of active plugins and their tools."""
        lines = []
        for plugin in self._plugins:
            tool_names = [t["function"]["name"] for t in plugin.tools]
            lines.append(f"• *{type(plugin).__name__}*: `{'`, `'.join(tool_names)}`")
        return "\n".join(lines) if lines else "No plugins registered."

    def requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires user approval before execution."""
        plugin = self._tool_map.get(tool_name)
        if plugin:
            return plugin.requires_approval(tool_name)
        return False

    def execute(self, tool_name: str, args_str: str) -> str:
        """
        Parse args and dispatch a tool call to the correct plugin.

        Args:
            tool_name: The function name as returned by the LLM.
            args_str:  Raw JSON string of arguments from the LLM.

        Returns:
            String result to feed back to the LLM as a tool response.
        """
        try:
            args = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            args = {}

        plugin = self._tool_map.get(tool_name)
        if not plugin:
            return f"[Error] Unknown tool: '{tool_name}'. Available: {list(self._tool_map.keys())}"

        try:
            result = plugin.execute(tool_name, args)
            return result if result is not None else "[Tool returned no output]"
        except Exception as e:
            return f"[Error] Tool '{tool_name}' raised an exception: {e}"
