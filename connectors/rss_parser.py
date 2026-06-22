import xml.etree.ElementTree as ET
import urllib.request

class RSSParser:
    """Zero-dependency RSS/Atom feed parser."""
    
    @staticmethod
    def parse(url: str, max_items: int = 5) -> list[dict]:
        """Fetch and parse an RSS or Atom feed."""
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 PmlabClaw/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_data = resp.read()
            
            root = ET.fromstring(xml_data)
            items = []
            
            # Handle RSS 2.0
            for item in root.findall(".//item")[:max_items]:
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                desc = item.findtext("description") or ""
                items.append({
                    "title": title.strip(), 
                    "link": link.strip(), 
                    "description": desc.strip()
                })
                
            # Handle Atom if RSS yielded no items
            if not items:
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                for entry in root.findall(".//atom:entry", ns)[:max_items]:
                    title = entry.findtext("atom:title", namespaces=ns) or ""
                    link_elem = entry.find("atom:link", namespaces=ns)
                    link = link_elem.attrib.get('href', '') if link_elem is not None else ""
                    desc = entry.findtext("atom:summary", namespaces=ns) or ""
                    if not desc:
                        desc = entry.findtext("atom:content", namespaces=ns) or ""
                        
                    items.append({
                        "title": title.strip(), 
                        "link": link.strip(), 
                        "description": desc.strip()
                    })
                    
            return items
        except Exception as e:
            print(f"[RSS Parser] Error parsing {url}: {e}")
            return []
