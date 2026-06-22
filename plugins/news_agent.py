import json
from plugins.base import PluginBase
from connectors.rss_parser import RSSParser

class NewsAgentPlugin(PluginBase):
    """
    Specialized agent for retrieving news and information from RSS feeds.
    """
    
    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "fetch_news",
                    "description": "Fetch latest news articles from an RSS or Atom feed URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "RSS/Atom feed URL"},
                            "limit": {"type": "integer", "description": "Max number of articles to fetch"}
                        },
                        "required": ["url"]
                    }
                }
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "fetch_news":
            url = args.get("url", "")
            limit = int(args.get("limit", 5))
            
            articles = RSSParser.parse(url, max_items=limit)
            if not articles:
                return f"No articles found or error parsing feed: {url}"
                
            return json.dumps(articles, indent=2)
            
        return f"Unknown tool: {tool_name}"
