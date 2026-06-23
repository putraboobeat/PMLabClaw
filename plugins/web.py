"""
plugins/web.py
==============
[BUILT-IN] Premium Web Intelligence Plugin.
Provides aggressive, multi-query web search and deep webpage reading.
Uses DuckDuckGo HTML scraping with robust parsing.
Zero dependencies — uses urllib only.
"""

import json
import re
import urllib.request
import urllib.error
import urllib.parse
import ssl
from html.parser import HTMLParser
from plugins.base import PluginBase


# Shared SSL context (skip verification for maximum compatibility)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


class WebPlugin(PluginBase):
    """Premium web intelligence: multi-search + deep read."""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "http_request",
                    "description": (
                        "Make an HTTP request to any URL. "
                        "Supports GET, POST, PUT, DELETE."
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
                                "description": "Request body (for POST/PUT)."
                            },
                            "headers": {
                                "type": "object",
                                "description": "Optional extra HTTP headers."
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
                        "Search the internet using DuckDuckGo. "
                        "Accepts EITHER a single 'query' string OR a 'queries' array for multiple simultaneous searches. "
                        "Always prefer using 'queries' array with 2-4 different search terms for comprehensive results. "
                        "Returns titles, snippets, and URLs from search results."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "A single search query string."
                            },
                            "queries": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Multiple search queries to run simultaneously for broader coverage."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results per query (default 5)."
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_webpage",
                    "description": (
                        "Read and extract the text content from a webpage URL. "
                        "Use this after search_web to 'click into' a result and read the full article, "
                        "documentation, or page content. Returns readable text."
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
            # Support both single query and multiple queries
            queries = args.get("queries", [])
            single = args.get("query", "")
            if not queries and single:
                queries = [single]
            if not queries:
                return "[Error] Provide 'query' (string) or 'queries' (array)."
            limit = args.get("limit", 5)
            return self._search_multiple(queries, limit)
        elif tool_name == "read_webpage":
            return self._read_webpage(url=args.get("url", ""))
        return None

    # ──────────────────────────────────────────────
    # HTTP Request
    # ──────────────────────────────────────────────

    def _http_request(self, url: str, method: str, body: str | None, headers: dict) -> str:
        if not url:
            return "[Error] URL is required."

        data = None
        if body:
            data = body.encode("utf-8") if isinstance(body, str) else body

        default_headers = {"User-Agent": _UA, "Content-Type": "application/json"}
        default_headers.update(headers or {})

        req = urllib.request.Request(url, data=data, headers=default_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8", errors="ignore")

                if "json" in content_type:
                    try:
                        parsed = json.loads(raw)
                        body_str = json.dumps(parsed, indent=2, ensure_ascii=False)
                    except Exception:
                        body_str = raw
                else:
                    body_str = raw[:3000]

                return f"*HTTP {status}*\n```\n{body_str}\n```"

        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")[:500]
            return f"[HTTP Error {e.code}] {err}"
        except Exception as e:
            return f"[Error] {e}"

    # ──────────────────────────────────────────────
    # Multi-query Web Search
    # ──────────────────────────────────────────────

    def _search_multiple(self, queries: list, limit: int = 5) -> str:
        """Run multiple searches and combine results."""
        all_sections = []
        for q in queries[:5]:  # Cap at 5 queries max
            result = self._search_single(q.strip(), limit)
            all_sections.append(result)
        return "\n\n" + "=" * 50 + "\n\n".join(all_sections)

    def _search_single(self, query: str, limit: int = 5) -> str:
        """Search DuckDuckGo HTML version and parse results."""
        if not query:
            return "[Error] Empty query."

        # Strategy 1: DuckDuckGo HTML POST
        results = self._ddg_html_search(query, limit)

        # Strategy 2: Fallback to DuckDuckGo Lite
        if not results:
            results = self._ddg_lite_search(query, limit)

        if not results:
            return f"🔍 Search '{query}': No results found. Try different keywords."

        output = f"🔍 **Search: '{query}'** — {len(results)} results:\n\n"
        for i, r in enumerate(results[:limit], 1):
            output += f"{i}. **{r['title']}**\n"
            output += f"   🔗 {r['url']}\n"
            if r.get('snippet'):
                output += f"   📝 {r['snippet']}\n"
            output += "\n"
        return output

    def _ddg_html_search(self, query: str, limit: int) -> list:
        """Parse DuckDuckGo HTML search results."""
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        headers = {
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8"
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                return self._parse_ddg_html(html, limit)
        except Exception as e:
            print(f"[WebPlugin] DDG HTML search error: {e}")
            return []

    def _ddg_lite_search(self, query: str, limit: int) -> list:
        """Fallback: Parse DuckDuckGo Lite search results."""
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        headers = {
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html"
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                return self._parse_ddg_lite(html, limit)
        except Exception as e:
            print(f"[WebPlugin] DDG Lite search error: {e}")
            return []

    def _parse_ddg_html(self, html: str, limit: int) -> list:
        """
        Parse html.duckduckgo.com results.
        Structure:
          <div class="result results_links results_links_deep web-result">
            <h2 class="result__title">
              <a class="result__a" href="URL">TITLE</a>
            </h2>
            <a class="result__snippet" href="...">SNIPPET</a>
          </div>
        """
        results = []

        # Extract result blocks using regex (more reliable than HTMLParser for this)
        # Find all result__a links (titles)
        title_pattern = re.compile(
            r'<a\s+[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )
        snippet_pattern = re.compile(
            r'<a\s+[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )

        titles = title_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title_html) in enumerate(titles[:limit]):
            title = self._strip_html(title_html).strip()
            snippet = ""
            if i < len(snippets):
                snippet = self._strip_html(snippets[i]).strip()

            # Clean the URL (DDG sometimes wraps URLs)
            clean_url = self._clean_ddg_url(url)

            if title and clean_url and not clean_url.startswith("/"):
                results.append({
                    "title": title,
                    "url": clean_url,
                    "snippet": snippet
                })

        return results

    def _parse_ddg_lite(self, html: str, limit: int) -> list:
        """Parse lite.duckduckgo.com results (simpler table format)."""
        results = []

        # Lite version uses simple links in table rows
        link_pattern = re.compile(
            r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*result-link[^"]*"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )
        # Also try without class
        if not link_pattern.findall(html):
            link_pattern = re.compile(
                r'<a[^>]+rel="nofollow"[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                re.DOTALL | re.IGNORECASE
            )

        snippet_pattern = re.compile(
            r'<td[^>]*class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>',
            re.DOTALL | re.IGNORECASE
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title_html) in enumerate(links[:limit]):
            title = self._strip_html(title_html).strip()
            snippet = ""
            if i < len(snippets):
                snippet = self._strip_html(snippets[i]).strip()

            if title and url:
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet
                })

        return results

    def _strip_html(self, html_str: str) -> str:
        """Remove HTML tags and decode entities."""
        text = re.sub(r'<[^>]+>', '', html_str)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        return re.sub(r'\s+', ' ', text).strip()

    def _clean_ddg_url(self, url: str) -> str:
        """Clean DuckDuckGo redirect URLs to get the actual target URL."""
        if "duckduckgo.com" in url and "uddg=" in url:
            match = re.search(r'uddg=([^&]+)', url)
            if match:
                return urllib.parse.unquote(match.group(1))
        return url

    # ──────────────────────────────────────────────
    # Deep Webpage Reader
    # ──────────────────────────────────────────────

    def _read_webpage(self, url: str) -> str:
        """Download a webpage and extract readable text content."""
        if not url:
            return "[Error] URL is required."

        headers = {
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8"
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()

                # Detect charset
                charset = "utf-8"
                if "charset=" in content_type.lower():
                    charset = content_type.lower().split("charset=")[-1].split(";")[0].strip()

                try:
                    html = raw.decode(charset, errors="ignore")
                except Exception:
                    html = raw.decode("utf-8", errors="ignore")

                # Extract text
                text = self._extract_text(html)

                if not text.strip():
                    return f"[Warning] Page at {url} returned no readable text."

                # Truncate to save tokens (but generous for deep reading)
                if len(text) > 12000:
                    text = text[:12000] + "\n\n...[TRUNCATED — page too long]"

                return f"📄 **Content from:** {url}\n\n{text}"

        except urllib.error.HTTPError as e:
            return f"[Error] HTTP {e.code}: {e.reason} for {url}"
        except Exception as e:
            return f"[Error] Failed to read {url}: {e}"

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML, removing scripts/styles/nav."""

        class _TextExtractor(HTMLParser):
            IGNORE_TAGS = {'script', 'style', 'noscript', 'meta', 'link',
                           'head', 'nav', 'footer', 'header', 'iframe', 'svg'}
            BLOCK_TAGS = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                          'li', 'tr', 'br', 'blockquote', 'pre', 'article', 'section'}

            def __init__(self):
                super().__init__()
                self.text_parts = []
                self.ignore_depth = 0

            def handle_starttag(self, tag, attrs):
                if tag in self.IGNORE_TAGS:
                    self.ignore_depth += 1
                elif tag in self.BLOCK_TAGS and self.text_parts:
                    self.text_parts.append("\n")

            def handle_endtag(self, tag):
                if tag in self.IGNORE_TAGS:
                    self.ignore_depth = max(0, self.ignore_depth - 1)

            def handle_data(self, data):
                if self.ignore_depth == 0:
                    cleaned = data.strip()
                    if cleaned:
                        self.text_parts.append(cleaned)

        extractor = _TextExtractor()
        try:
            extractor.feed(html)
        except Exception:
            pass

        text = " ".join(extractor.text_parts)
        # Clean up excessive whitespace/newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()
