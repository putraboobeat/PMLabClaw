"""
plugins/developer.py
====================
AI Plugin Generator.
Allows the LLM to write new plugins and save them to the plugins directory.
"""

import os
from plugins.base import PluginBase
from core.event_bus import bus


_PLUGINS_DIR = os.path.dirname(os.path.abspath(__file__))


class DeveloperPlugin(PluginBase):
    """Self-extension tools."""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_plugin",
                    "description": (
                        "Generate and save a new python plugin file. "
                        "The plugin must subclass PluginBase and implement tools/execute. "
                        "Do not include Markdown block backticks in the python_code, just raw code."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "Name of the file, e.g., 'database.py'"
                            },
                            "python_code": {
                                "type": "string",
                                "description": "The complete raw python code for the plugin."
                            }
                        },
                        "required": ["filename", "python_code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reload_plugins",
                    "description": "Trigger a hot-reload of all plugins. Call this after creating or editing a plugin.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]

    def requires_approval(self, tool_name: str) -> bool:
        # Saving new python code is high risk. Must be approved.
        if tool_name == "create_plugin":
            return True
        return False

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "create_plugin":
            return self._create_plugin(args.get("filename", ""), args.get("python_code", ""))
        elif tool_name == "reload_plugins":
            bus.emit("reload_plugins")
            return "✅ Plugins reloaded successfully."
        return None

    def _create_plugin(self, filename: str, python_code: str) -> str:
        if not filename.endswith(".py"):
            filename += ".py"
            
        # Prevent path traversal
        if "/" in filename or "\\" in filename or ".." in filename:
            return "[Error] Invalid filename. Just provide the base name."

        filepath = os.path.join(_PLUGINS_DIR, filename)
        
        try:
            with open(filepath, "w") as f:
                f.write(python_code)
            return f"✅ Plugin `{filename}` created successfully. Call `reload_plugins` to activate it."
        except Exception as e:
            return f"[Error] Failed to write plugin: {e}"
