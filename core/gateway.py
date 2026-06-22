from abc import ABC, abstractmethod

class BaseGateway(ABC):
    """
    Abstract Base Class for message gateways (Telegram, WhatsApp, etc).
    All gateways must implement these basic functions.
    """
    
    @abstractmethod
    def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> None:
        """Send a text message to the specified chat_id."""
        pass

    @abstractmethod
    def send_action(self, chat_id: str, action: str = "typing") -> None:
        """Send a chat action (like typing) to the specified chat_id."""
        pass
