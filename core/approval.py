"""
core/approval.py
================
Approval system for high-risk actions.
Intercepts tool calls that require manual user confirmation.
"""

import time
import uuid
from typing import Callable, Any
from core.memory import memory_db


class ApprovalSystem:
    """
    Manages pending actions that require user confirmation.
    Stores pending requests in SQLite memory so they survive restarts.
    """

    def request_approval(self, chat_id: str, tool_name: str, args: dict, reason: str = "") -> str:
        """
        Create a pending approval request.
        Returns the request ID.
        """
        request_id = str(uuid.uuid4())[:8]  # Short ID for easy typing
        
        pending_data = {
            "chat_id": chat_id,
            "tool_name": tool_name,
            "args": args,
            "reason": reason,
            "timestamp": time.time()
        }
        
        # Save to KV store with a specific prefix
        memory_db.set_kv(f"pending_approval_{request_id}", pending_data)
        
        return request_id

    def get_pending(self, request_id: str) -> dict | None:
        """Retrieve a pending request by ID."""
        return memory_db.get_kv(f"pending_approval_{request_id}")

    def resolve(self, request_id: str, approved: bool) -> dict | None:
        """
        Mark a request as resolved (approved or denied).
        Returns the pending data if it existed, so the agent can execute it.
        """
        data = self.get_pending(request_id)
        if data:
            memory_db.delete_kv(f"pending_approval_{request_id}")
            if approved:
                return data
        return None

    def clear_expired(self, max_age_seconds: int = 3600):
        """Cleanup old pending requests (future optimization)."""
        pass


approval_system = ApprovalSystem()
