"""
plugins/base.py
===============
Abstract base class that every PmlabClaw plugin must inherit.

A plugin has exactly two responsibilities:
  1. Declare its tools (the JSON schema the LLM uses to call them)
  2. Execute those tools when called by the dispatcher

That's it. Simple. Powerful. Extensible.
"""

from abc import ABC, abstractmethod


class PluginBase(ABC):
    """
    Base class for all PmlabClaw plugins.

    To create a new plugin:
        1. Create a file in plugins/my_plugin.py
        2. Subclass PluginBase
        3. Implement `tools` and `execute`
        4. Register it in main.py: dispatcher.register(MyPlugin())

    Example:
        class MyPlugin(PluginBase):

            @property
            def tools(self):
                return [{
                    "type": "function",
                    "function": {
                        "name": "say_hello",
                        "description": "Say hello to someone.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "The person's name."}
                            },
                            "required": ["name"]
                        }
                    }
                }]

            def execute(self, tool_name: str, args: dict) -> str:
                if tool_name == "say_hello":
                    return f"Hello, {args['name']}!"
    """

    def __init__(self, *args, **kwargs):
        """
        Base constructor. Accepts generic args/kwargs so PluginLoader can safely
        pass global context (like telegram_client) to all plugins. 
        """
        pass

    @property
    @abstractmethod
    def tools(self) -> list[dict]:
        """
        Return a list of tool definitions in OpenAI function-calling format.
        These are passed directly to the LLM so it knows what it can call.
        """
        ...

    @abstractmethod
    def execute(self, tool_name: str, args: dict) -> str | None:
        """
        Execute a tool by name with the provided arguments.

        Args:
            tool_name: The name of the tool to execute (matches a tool in self.tools).
            args:      Parsed dictionary of arguments from the LLM.

        Returns:
            A string result to return to the LLM, or None.
        """
        ...

    def requires_approval(self, tool_name: str) -> bool:
        """
        Override this to return True for high-risk tools that need manual confirmation.
        """
        return False
