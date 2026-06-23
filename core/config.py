"""
core/config.py
==============
Centralized configuration loader.
Reads from .env file and environment variables.
All other modules import settings from here.
"""

import os


def _load_dotenv(dotenv_path):
    """Parse and load a .env file into os.environ."""
    if not os.path.exists(dotenv_path):
        return
    with open(dotenv_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


# Auto-load .env from the project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))


class Config:
    """
    Single source of truth for all configuration.
    Add new config keys here as the project grows.
    """

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ALLOWED_CHAT_ID: str = os.getenv("ALLOWED_CHAT_ID", "")

    # --- WhatsApp (Evolution API / WAHA) ---
    WHATSAPP_API_URL: str = os.getenv("WHATSAPP_API_URL", "")
    WHATSAPP_API_KEY: str = os.getenv("WHATSAPP_API_KEY", "")
    ALLOWED_WA_NUMBER: str = os.getenv("ALLOWED_WA_NUMBER", "")
    WHATSAPP_WEBHOOK_PORT: int = int(os.getenv("WHATSAPP_WEBHOOK_PORT", "8080"))

    # --- StarSender V3 (WhatsApp Gateway) ---
    STARSENDER_API_KEY: str = os.getenv("STARSENDER_API_KEY", "")
    STARSENDER_WEBHOOK_PORT: int = int(os.getenv("STARSENDER_WEBHOOK_PORT", "8081"))

    # --- LLM API ---
    API_KEY: str = os.getenv("API_KEY", "")
    API_BASE_URL: str = os.getenv("API_BASE_URL", "https://agentrouter.org/v1")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "deepseek-v4-flash")

    # --- Agent Behavior ---
    MAX_TOOL_ITERATIONS: int = int(os.getenv("MAX_TOOL_ITERATIONS", "10"))
    MAX_HISTORY_LENGTH: int = int(os.getenv("MAX_HISTORY_LENGTH", "30"))
    TELEGRAM_POLL_TIMEOUT: int = int(os.getenv("TELEGRAM_POLL_TIMEOUT", "50"))
    SHELL_TIMEOUT: int = int(os.getenv("SHELL_TIMEOUT", "30"))

    # --- Identity ---
    BOT_NAME: str = "PmlabClaw"
    VERSION: str = "1.0.0"

    @classmethod
    def validate(cls):
        """Validate that all required credentials are present."""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN")
        if not cls.API_KEY:
            errors.append("API_KEY")
        if not cls.ALLOWED_CHAT_ID:
            errors.append("ALLOWED_CHAT_ID")
        if errors:
            raise EnvironmentError(
                f"[Config] Missing required environment variables: {', '.join(errors)}\n"
                f"Please copy .env.example to .env and fill in the values."
            )


# Singleton instance
cfg = Config()
