"""
core/workflow.py
================
Workflow and Recipe Engine for PmlabClaw X.
Executes sequence of tool calls defined in JSON format.

Example Workflow JSON:
{
    "name": "daily_content",
    "steps": [
        {
            "name": "generate_article",
            "tool": "web_search",
            "args": {"query": "AI news today"}
        },
        {
            "name": "summarize",
            "prompt": "Summarize the following: {{generate_article.result}}"
        }
    ]
}
"""

import os
import json
import re
from typing import Any

from core.dispatcher import Dispatcher
from core.llm import LLMClient


_RECIPES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "recipes"
)


class WorkflowEngine:
    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher
        self.llm = LLMClient()
        os.makedirs(_RECIPES_DIR, exist_ok=True)

    def load_recipe(self, recipe_name: str) -> dict | None:
        """Load a JSON recipe by name."""
        if not recipe_name.endswith(".json"):
            recipe_name += ".json"
            
        filepath = os.path.join(_RECIPES_DIR, recipe_name)
        if not os.path.exists(filepath):
            return None
            
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Workflow] Error loading {recipe_name}: {e}")
            return None

    def run_recipe(self, recipe_name: str, context: dict = None) -> dict:
        """
        Execute a recipe sequentially.
        State is carried over between steps.
        """
        recipe = self.load_recipe(recipe_name)
        if not recipe:
            return {"status": "error", "message": f"Recipe '{recipe_name}' not found."}

        state = context or {}
        
        for step in recipe.get("steps", []):
            step_name = step.get("name", "unnamed_step")
            
            # 1. Substitute variables in arguments
            tool = step.get("tool")
            prompt = step.get("prompt")
            
            if tool:
                # Direct tool execution
                raw_args = step.get("args", {})
                args_str = json.dumps(raw_args)
                args_str = self._substitute_vars(args_str, state)
                
                try:
                    result = self.dispatcher.execute(tool, args_str)
                    state[step_name] = {"result": result}
                except Exception as e:
                    state[step_name] = {"error": str(e)}
                    if step.get("abort_on_error", True):
                        break
                        
            elif prompt:
                # LLM execution (reasoning/summarization step)
                real_prompt = self._substitute_vars(prompt, state)
                messages = [{"role": "user", "content": real_prompt}]
                try:
                    response = self.llm.chat(messages, tools=None)
                    result_text = response["choices"][0]["message"]["content"]
                    state[step_name] = {"result": result_text}
                except Exception as e:
                    state[step_name] = {"error": str(e)}
                    if step.get("abort_on_error", True):
                        break

        return {"status": "success", "state": state}

    def _substitute_vars(self, text: str, state: dict) -> str:
        """Replace {{step_name.key}} with actual values from state."""
        def repl(match):
            path = match.group(1).split('.')
            val = state
            for key in path:
                if isinstance(val, dict):
                    val = val.get(key, "")
                else:
                    return ""
            return str(val)

        return re.sub(r'\{\{([^}]+)\}\}', repl, text)
