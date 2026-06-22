import json
import urllib.request
import urllib.error
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from core.config import cfg
from core.gateway import BaseGateway


class WhatsAppClient(BaseGateway):
    """
    WhatsApp API client using HTTP requests.
    Designed for Evolution API / WAHA endpoints.
    """

    def _post(self, url: str, payload: dict) -> dict:
        if not cfg.WHATSAPP_API_URL:
            return {}
            
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "apikey": cfg.WHATSAPP_API_KEY,
            "Authorization": f"Bearer {cfg.WHATSAPP_API_KEY}" # Supports both header types
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[WhatsApp] Error: {e}")
            return {}

    def send_message(self, chat_id: str, text: str, parse_mode: str = "") -> None:
        """Send text message to WhatsApp number."""
        if not cfg.WHATSAPP_API_URL:
            return
            
        # Example payload for Evolution API (message/sendText)
        # Adapt this payload to your specific gateway if needed
        url = f"{cfg.WHATSAPP_API_URL.rstrip('/')}/message/sendText"
        payload = {
            "number": chat_id,
            "text": text
        }
        self._post(url, payload)

    def send_action(self, chat_id: str, action: str = "typing") -> None:
        """Send presence (typing/recording)."""
        if not cfg.WHATSAPP_API_URL:
            return
            
        url = f"{cfg.WHATSAPP_API_URL.rstrip('/')}/chat/sendPresence"
        presence = "composing" if action == "typing" else "available"
        payload = {
            "number": chat_id,
            "presence": presence
        }
        self._post(url, payload)


def start_whatsapp_webhook(agent, gateway: WhatsAppClient):
    """
    Starts an HTTP server in a background thread to receive WhatsApp webhooks.
    """
    if not cfg.WHATSAPP_API_URL:
        print("[WhatsApp] WHATSAPP_API_URL not set. Webhook server disabled.")
        return

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_response(400)
                self.end_headers()
                return

            body = self.rfile.read(content_length).decode("utf-8")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            
            try:
                data = json.loads(body)
            except Exception:
                return
                
            # Parse message based on Evolution API webhook format
            # Evolution API wraps messages in messages[0] or data
            msg_data = data.get("data", data)
            
            if "key" in msg_data and "message" in msg_data:
                # Normal Evolution API webhook format
                remote_jid = msg_data.get("key", {}).get("remoteJid", "")
                sender = remote_jid.split("@")[0]
                
                # Extract text (conversation or extendedTextMessage)
                msg_content = msg_data.get("message", {})
                text = msg_content.get("conversation", "")
                if not text and "extendedTextMessage" in msg_content:
                    text = msg_content["extendedTextMessage"].get("text", "")
                
                if not text:
                    return

                # Security Gate
                if cfg.ALLOWED_WA_NUMBER and sender != cfg.ALLOWED_WA_NUMBER:
                    print(f"[Security] Blocked WA message from: {sender}")
                    return
                    
                # Handle via Agent
                try:
                    # Use a new thread so the webhook responds immediately
                    threading.Thread(target=agent.handle_message, args=(remote_jid, text, gateway)).start()
                except Exception as e:
                    print(f"[WhatsApp] Agent error: {e}")

        def log_message(self, format, *args):
            pass # Disable default HTTP logging to keep console clean

    server = HTTPServer(("0.0.0.0", cfg.WHATSAPP_WEBHOOK_PORT), WebhookHandler)
    print(f"[WhatsApp] Webhook server listening on port {cfg.WHATSAPP_WEBHOOK_PORT}")
    
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
