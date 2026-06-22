import json
from plugins.base import PluginBase

class ContentFactoryPlugin(PluginBase):
    """
    Specialized agent for drafting and managing social media content.
    """
    
    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "draft_social_post",
                    "description": "Draft a social media post for a given topic or text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "The topic, article content, or link"},
                            "platform": {"type": "string", "description": "Platform (e.g., Twitter, LinkedIn, Instagram)"}
                        },
                        "required": ["topic", "platform"]
                    }
                }
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "draft_social_post":
            topic = args.get("topic", "")
            platform = args.get("platform", "Twitter")
            
            # Since this is a specialized agent logic, we can instruct the main LLM 
            # to draft it using its own conversational abilities based on this output.
            return (
                f"[System Instruction]\n"
                f"You must now act as an expert Social Media Manager.\n"
                f"Please generate a highly engaging {platform} post about the following topic:\n\n"
                f"{topic}\n\n"
                f"Ensure you format it correctly for the requested platform with appropriate tone, emojis, and hashtags."
            )
            
        return f"Unknown tool: {tool_name}"
