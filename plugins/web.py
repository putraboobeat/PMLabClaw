"""
plugins/web.py
==============
[BUILT-IN] HTTP request plugin.
Allows the LLM to fetch URLs, call webhooks, or hit external APIs.
Uses urllib only — zero dependencies.
"""

import json
import urllib.request
import urllib.error
import urllib.parse
from plugins.base import PluginBase


class WebPlugin(PluginBase):
    """Fetch URLs and call HTTP endpoints."""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "http_request",
                    "description": (
                        "Make an HTTP request to any URL. "
                        "Supports GET, POST, PUT, DELETE. "
                        "Use for calling webhooks, checking APIs, or fetching web content."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The full URL to request."
                            },
                            "method": {
                                "type": "string",
                                "enum": ["GET", "POST", "PUT", "DELETE"],
                                "description": "HTTP method. Default: GET"
                            },
                            "body": {
                                "type": "string",
                                "description": "Request body as a JSON string (for POST/PUT)."
                            },
                            "headers": {
                                "type": "object",
                                "description": "Optional extra HTTP headers as key-value pairs."
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": (
                        "Search the internet (DuckDuckGo) to find information, news, or articles. "
                        "Returns a list of titles, snippets, and URLs."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "queries": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of search queries to execute simultaneously (e.g. ['latest AI news', 'bitcoin price'])."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results to return per query (default 3)."
                            }
                        },
                        "required": ["queries"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_webpage",
                    "description": (
                        "Read the textual content of a specific webpage URL. "
                        "Use this to 'click' into a search result and read the full article or documentation. "
                        "Returns the readable text from the page."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The full URL to read."
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "http_request":
            return self._http_request(
                url=args.get("url", ""),
                method=args.get("method", "GET").upper(),
                body=args.get("body"),
                headers=args.get("headers", {})
            )
        elif tool_name == "search_web":
            queries = args.get("queries", [])
            if not queries and "query" in args:
                queries = [args["query"]]
            return self._search_web_multiple(
                queries=queries,
                limit=args.get("limit", 3)
            )
        elif tool_name == "read_webpage":
            return self._read_webpage(url=args.get("url", ""))
        return None

    def _http_request(self, url: str, method: str, body: str | None, headers: dict) -> str:
        if not url:
            return "[Error] URL is required."

        data = None
        if body:
            data = body.encode("utf-8") if isinstance(body, str) else body

        default_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36", "Content-Type": "application/json"}
        default_headers.update(headers or {})

        req = urllib.request.Request(url, data=data, headers=default_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8", errors="ignore")

                # Pretty-print JSON if applicable
                if "json" in content_type:
                    try:
                        parsed = json.loads(raw)
                        body_str = json.dumps(parsed, indent=2, ensure_ascii=False)
                    except Exception:
                        body_str = raw
                else:
                    body_str = raw[:2000]  # Truncate large HTML

                return f"*HTTP {status}*\n```\n{body_str}\n```"

        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")[:500]
            return f"[HTTP Error {e.code}] {err}"
        except Exception as e:
            return f"[Error] {e}"

    def _search_web_multiple(self, queries: list, limit: int = 3) -> str:
        if not queries:
            return "[Error] queries array is required."
        
        results = []
        for q in queries:
            res = self._search_web_single(q, limit)
            results.append(res)
        return "\n\n---\n\n".join(results)

    def _search_web_single(self, query: str, limit: int = 3) -> str:
        """Search DuckDuckGo Lite via HTML scraping."""
        if not query:
            return "[Error] Query is required."
        
        from html.parser import HTMLParser
        
        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.in_result = False
                self.in_title = False
                self.in_snippet = False
                self.current_title = ""
                self.current_url = ""
                self.current_snippet = ""

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                cls = attrs_dict.get("class", "")
                
                # lite.duckduckgo.com uses result-snippet and result-title
                if tag == "tr":
                    pass
                elif tag == "a" and "result-snippet" in cls:
                    self.in_snippet = True
                    if "href" in attrs_dict:
                        self.current_url = attrs_dict["href"]
                elif tag == "a" and "result-title" in cls: # for html.duckduckgo.com it's result__url
                    pass
                elif tag == "a" and "result__url" in cls:
                    self.in_title = True
                    if "href" in attrs_dict:
                        self.current_url = attrs_dict["href"]
                elif tag == "a" and "result__snippet" in cls:
                    self.in_snippet = True

            def handle_data(self, data):
                if self.in_title:
                    self.current_title += data.strip() + " "
                elif self.in_snippet:
                    self.current_snippet += data.strip() + " "

            def handle_endtag(self, tag):
                if tag == "a":
                    if self.in_title:
                        self.in_title = False
                    if self.in_snippet:
                        self.in_snippet = False
                        if self.current_title and self.current_url:
                            # Avoid duplicates or internal links
                            if not self.current_url.startswith("/"):
                                self.results.append({
                                    "title": self.current_title.strip(),
                                    "url": self.current_url,
                                    "snippet": self.current_snippet.strip()
                                })
                            self.current_title = ""
                            self.current_url = ""
                            self.current_snippet = ""
        
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            import ssl
            # Bypass ssl check locally if needed
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                parser = DDGParser()
                parser.feed(html)
                
                if not parser.results:
                    return "No results found or DuckDuckGo blocked the request."
                
                output = f"Top {limit} Results for '{query}':\n\n"
                for i, res in enumerate(parser.results[:limit]):
                    output += f"{i+1}. {res['title']}\n"
                    output += f"   URL: {res['url']}\n"
                    output += f"   Snippet: {res['snippet']}\n\n"
                
                return output
                
        except Exception as e:
            return f"[Error] Search failed for '{query}': {e}"

    def _read_webpage(self, url: str) -> str:
        """Download webpage and extract readable text using basic HTML parsing."""
        if not url:
            return "[Error] URL is required."
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        req = urllib.request.Request(url, headers=headers)
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()
                
                if "charset=" in content_type.lower():
                    charset = content_type.lower().split("charset=")[-1]
                else:
                    charset = "utf-8"
                
                try:
                    html = raw.decode(charset, errors="ignore")
                except:
                    html = raw.decode("utf-8", errors="ignore")
                
                from html.parser import HTMLParser
                class TextExtractor(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.text = []
                        self.ignore = False
                        self.ignore_tags = {'script', 'style', 'noscript', 'meta', 'link', 'head'}
                    def handle_starttag(self, tag, attrs):
                        if tag in self.ignore_tags:
                            self.ignore = True
                    def handle_endtag(self, tag):
                        if tag in self.ignore_tags:
                            self.ignore = False
                    def handle_data(self, data):
                        if not self.ignore:
                            cleaned = data.strip()
                            if cleaned:
                                self.text.append(cleaned)
                
                parser = TextExtractor()
                parser.feed(html)
                
                text_content = "\n".join(parser.text)
                # Truncate if insanely large to save tokens
                if len(text_content) > 15000:
                    text_content = text_content[:15000] + "\n\n...[TRUNCATED]"
                    
                return f"--- CONTENT FOR {url} ---\n\n{text_content}"
                
        except urllib.error.HTTPError as e:
            return f"[Error] HTTP {e.code}: {e.reason}"
        except Exception as e:
            return f"[Error] Failed to read webpage: {e}"

