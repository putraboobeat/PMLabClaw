"""
plugins/__init__.py
===================
Auto-discovers and exports all built-in plugins.
"""

from plugins.base import PluginBase
from plugins.shell import ShellPlugin
from plugins.system import SystemPlugin
from plugins.scheduler import SchedulerPlugin
from plugins.web import WebPlugin

__all__ = [
    "PluginBase",
    "ShellPlugin",
    "SystemPlugin",
    "SchedulerPlugin",
    "WebPlugin",
]
