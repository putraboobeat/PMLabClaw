"""
plugins/workflow_runner.py
==========================
Allows the LLM to run pre-defined JSON workflows from the recipes/ folder.
"""

import json
from plugins.base import PluginBase
from core.workflow import WorkflowEngine


class WorkflowRunnerPlugin(PluginBase):
    """Exposes the WorkflowEngine to the LLM."""

    def __init__(self, dispatcher, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workflow_engine = WorkflowEngine(dispatcher)

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_workflow",
                    "description": "Run a predefined JSON workflow from the recipes directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recipe_name": {
                                "type": "string",
                                "description": "The name of the recipe (e.g. 'daily_news')"
                            },
                            "context": {
                                "type": "string",
                                "description": "Optional JSON string containing initial context/variables."
                            }
                        },
                        "required": ["recipe_name"]
                    }
                }
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "run_workflow":
            recipe_name = args.get("recipe_name", "")
            context_str = args.get("context", "{}")
            
            try:
                context = json.loads(context_str)
            except Exception:
                context = {}
                
            result = self.workflow_engine.run_recipe(recipe_name, context)
            
            if result.get("status") == "success":
                # Only return the final step's result to avoid overwhelming the LLM
                state = result.get("state", {})
                last_step = list(state.keys())[-1] if state else "unknown"
                last_result = state.get(last_step, {})
                return f"Workflow completed successfully. Final step ({last_step}) result: {json.dumps(last_result)[:500]}"
            else:
                return f"Workflow failed: {result.get('message', 'Unknown error')}"
        return None
