"""
core/plugin_loader.py
=====================
Dynamic plugin discovery and loader.
Scans the plugins/ directory, imports Python files, and instantiates any
class that subclasses PluginBase.

Supports hot-reloading: `reload_plugins()` will re-read files and rebuild the tool map.
"""

import os
import sys
import importlib
import inspect
from typing import Type

from core.dispatcher import Dispatcher
from plugins.base import PluginBase


_PLUGINS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins"
)


class PluginLoader:
    """
    Handles auto-discovery and loading of plugins.
    """

    def __init__(self, dispatcher: Dispatcher, *args_for_plugins, **kwargs_for_plugins):
        """
        Args:
            dispatcher: The registry to register loaded plugins into.
            args_for_plugins: Arguments passed to plugin constructors (e.g., telegram_client).
        """
        self.dispatcher = dispatcher
        self._plugin_args = args_for_plugins
        self._plugin_kwargs = kwargs_for_plugins

    def load_all(self):
        """Scan the plugins directory and load all valid plugins."""
        # Ensure plugins dir exists
        os.makedirs(_PLUGINS_DIR, exist_ok=True)
        
        # Make sure the root is in path so we can import plugins.xxx
        root_dir = os.path.dirname(_PLUGINS_DIR)
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        print("[PluginLoader] Scanning for plugins...")
        
        # Clear existing tools in dispatcher to prepare for clean load
        self.dispatcher.clear()

        for filename in os.listdir(_PLUGINS_DIR):
            if filename.endswith(".py") and not filename.startswith("_"):
                module_name = f"plugins.{filename[:-3]}"
                self._load_module(module_name)

    def _load_module(self, module_name: str):
        try:
            # If already loaded, we must reload it to get fresh code
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
                
            # Find all classes in the module that inherit from PluginBase
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if obj is not PluginBase and issubclass(obj, PluginBase):
                    # Don't instantiate abstract classes
                    if not inspect.isabstract(obj):
                        try:
                            # Instantiate and register
                            instance = obj(*self._plugin_args, **self._plugin_kwargs)
                            self.dispatcher.register(instance)
                        except Exception as e:
                            print(f"[PluginLoader] Failed to init {name} in {module_name}: {e}")
                            
        except Exception as e:
            print(f"[PluginLoader] Failed to load module {module_name}: {e}")

