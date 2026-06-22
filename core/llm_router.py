"""
core/llm_router.py
==================
Multi-model router for OpenRouter.
Routes requests to the cheapest or most capable model based on task complexity.
Always prioritizes token efficiency unless explicitly requested otherwise.
"""

from core.config import cfg
from core.llm import LLMClient


class LLMRouter:
    """
    Intelligently routes prompts to different LLMs based on cost/capability requirements.
    """

    def __init__(self):
        self.default_client = LLMClient()
        # In a real OpenRouter setup, we'd have a dict of clients for different models.
        # For now, we use the default client but can override the MODEL_NAME on the fly
        # if the client supported it. Since LLMClient pulls from cfg.MODEL_NAME directly,
        # we might need to modify LLMClient slightly, or just use the default for Phase 1.

    def chat(self, messages: list[dict], tools: list[dict] | None = None, category: str = "cheap") -> dict:
        """
        Route the chat to the appropriate model.
        Categories: planner, reasoning, writing, coding, cheap.
        """
        
        # [FUTURE EXPANSION]
        # Here we would map categories to specific OpenRouter model IDs.
        # e.g.,
        # model_map = {
        #     "cheap": "google/gemini-flash-1.5",
        #     "reasoning": "openai/o1",
        #     "coding": "anthropic/claude-3.5-sonnet",
        #     "writing": "anthropic/claude-3-opus"
        # }
        # target_model = model_map.get(category, cfg.MODEL_NAME)
        
        # For Phase 1, we route everything through the token-efficient default model.
        # This keeps the core small and adheres to "Hemat Token".
        return self.default_client.chat(messages, tools)

