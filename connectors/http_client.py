import json
import urllib.request
import urllib.error
import urllib.parse

class HTTPClient:
    """Zero-dependency HTTP client mimicking requests library."""
    
    @staticmethod
    def get(url: str, headers: dict = None, timeout: int = 15) -> dict:
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode('utf-8')
                if resp.headers.get_content_type() == 'application/json':
                    try:
                        content = json.loads(content)
                    except Exception:
                        pass
                return {"status": resp.status, "data": content}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "error": str(e)}
        except Exception as e:
            return {"status": 0, "error": str(e)}
            
    @staticmethod
    def post(url: str, json_data: dict = None, headers: dict = None, timeout: int = 15) -> dict:
        headers = headers or {}
        data = None
        if json_data is not None:
            data = json.dumps(json_data).encode("utf-8")
            headers["Content-Type"] = "application/json"
            
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode('utf-8')
                if resp.headers.get_content_type() == 'application/json':
                    try:
                        content = json.loads(content)
                    except Exception:
                        pass
                return {"status": resp.status, "data": content}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "error": str(e)}
        except Exception as e:
            return {"status": 0, "error": str(e)}
