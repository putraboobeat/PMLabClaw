import json
import urllib.request
import urllib.error
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from core.config import cfg
from core.gateway import BaseGateway


class StarSenderClient(BaseGateway):
    """
    StarSender V3 API client for sending WhatsApp messages.
    """

    def _post(self, url: str, payload: dict) -> dict:
        if not cfg.STARSENDER_API_KEY:
            return {}
            
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": cfg.STARSENDER_API_KEY
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[StarSender] Error sending request: {e}")
            return {}

    def send_message(self, chat_id: str, text: str, parse_mode: str = "") -> None:
        """Send text message to WhatsApp number via StarSender."""
        if not cfg.STARSENDER_API_KEY:
            return
            
        url = "https://api.starsender.online/api/send"
        
        # Format number (StarSender usually expects standard format without + or spaces)
        clean_number = chat_id.replace("+", "").replace(" ", "").replace("-", "")
        if clean_number.startswith("0"):  # Convert local to international if needed
            clean_number = "62" + clean_number[1:]
            
        payload = {
            "messageType": "text",
            "to": clean_number,
            "body": text
        }
        self._post(url, payload)

    def send_action(self, chat_id: str, action: str = "typing") -> None:
        """Send presence (typing/recording). Not universally supported in StarSender, so ignored."""
        pass


def start_starsender_webhook(agent, gateway: StarSenderClient):
    """
    Starts an HTTP server in a background thread to receive StarSender webhooks.
    """
    if not cfg.STARSENDER_API_KEY:
        return

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_response(400)
                self.end_headers()
                return

            body = self.rfile.read(content_length).decode("utf-8")
            
            # Fast response back to StarSender
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')
            
            try:
                data = json.loads(body)
            except Exception:
                return
                
            # Parse StarSender Webhook Payload
            # Example: {"message": "Hello", "from": "62812...", "timestamp": ...}
            text = data.get("message", "")
            sender = data.get("from", "")
            
            # Kadang ID grup atau @s.whatsapp.net ikut terlampir, bersihkan:
            sender_clean = sender.split("@")[0]
            
            if not text or not sender_clean:
                return

            # --- Security Gate ---
            # By default, only allow ALLOWED_WA_NUMBER to prevent unauthorized terminal access
            if cfg.ALLOWED_WA_NUMBER and sender_clean != cfg.ALLOWED_WA_NUMBER:
                print(f"[Security] Blocked unauthorized WA message from: {sender_clean}")
                # Optional: You can reply 'Unauthorized' if you want.
                # gateway.send_message(sender_clean, "⛔ Anda tidak memiliki akses ke asisten ini.")
                return
                
            # --- Handle via Agent ---
            try:
                # Use a new thread so the webhook responds immediately without waiting for LLM
                threading.Thread(target=agent.handle_message, args=(sender_clean, text, gateway)).start()
            except Exception as e:
                print(f"[StarSender] Agent error: {e}")

        def log_message(self, format, *args):
            pass # Disable default HTTP logging to keep console clean

    server = HTTPServer(("0.0.0.0", cfg.STARSENDER_WEBHOOK_PORT), WebhookHandler)
    print(f"[StarSender] Webhook server listening on port {cfg.STARSENDER_WEBHOOK_PORT}")
    
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
