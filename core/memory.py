"""
core/memory.py
==============
SQLite-based memory system with FTS5 (Full Text Search).
Provides robust persistent storage for preferences, workflows, templates,
and general knowledge without the overhead of a Vector Database.

Zero dependencies, extremely lightweight.
"""

import os
import sqlite3
import json
from typing import Any


_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "pmlabclaw_memory.sqlite"
)


class MemoryDB:
    """
    SQLite wrapper providing Key-Value storage and FTS5 knowledge search.
    """

    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        # Check same thread false to allow access from web/telegram threads
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._get_conn() as conn:
            # 1. Key-Value store for preferences, simple states
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. FTS5 table for searchable knowledge, workflows, templates
            # Requires sqlite3 compiled with FTS5 (standard in Python 3.8+)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge 
                USING fts5(category, title, content, tags)
            """)

    # ── Key-Value Operations ──

    def set_kv(self, key: str, value: Any) -> None:
        """Store a value (automatically serialized to JSON if dict/list)."""
        if isinstance(value, (dict, list)):
            val_str = json.dumps(value)
        else:
            val_str = str(value)
            
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO kv_store (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET 
                    value=excluded.value, 
                    updated_at=CURRENT_TIMESTAMP
                """, 
                (key, val_str)
            )

    def get_kv(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key. Attempts to parse JSON."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,))
            row = cur.fetchone()
            if not row:
                return default
            
            val_str = row["value"]
            try:
                return json.loads(val_str)
            except json.JSONDecodeError:
                return val_str

    def delete_kv(self, key: str) -> bool:
        """Delete a key-value pair."""
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
            return cur.rowcount > 0

    # ── Knowledge / FTS5 Operations ──

    def add_knowledge(self, category: str, title: str, content: str, tags: str = "") -> None:
        """
        Add a searchable document to the knowledge base.
        Category examples: 'workflow', 'recipe', 'preference', 'fact'.
        """
        with self._get_conn() as conn:
            # Check if title already exists to avoid duplicates (FTS5 doesn't enforce UNIQUE constraints)
            # So we manually delete the old one first if it matches exactly
            conn.execute(
                "DELETE FROM knowledge WHERE category = ? AND title = ?", 
                (category, title)
            )
            conn.execute(
                "INSERT INTO knowledge (category, title, content, tags) VALUES (?, ?, ?, ?)",
                (category, title, content, tags)
            )

    def search_knowledge(self, query: str, category: str = None, limit: int = 5) -> list[dict]:
        """
        Search knowledge using FTS5 match syntax.
        Matches against all text fields (title, content, tags).
        """
        sql = "SELECT category, title, content, tags FROM knowledge WHERE knowledge MATCH ?"
        params = [query]
        
        if category:
            # Filter by specific category
            sql += " AND category = ?"
            params.append(category)
            
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        
        results = []
        with self._get_conn() as conn:
            try:
                cur = conn.execute(sql, params)
                for row in cur:
                    results.append(dict(row))
            except sqlite3.OperationalError as e:
                # Fallback to standard LIKE if FTS query syntax is invalid
                print(f"[Memory] FTS search failed: {e}. Falling back to LIKE.")
                like_q = f"%{query}%"
                fallback_sql = "SELECT category, title, content, tags FROM knowledge WHERE (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
                fb_params = [like_q, like_q, like_q]
                
                if category:
                    fallback_sql += " AND category = ?"
                    fb_params.append(category)
                    
                fallback_sql += " LIMIT ?"
                fb_params.append(limit)
                
                cur = conn.execute(fallback_sql, fb_params)
                for row in cur:
                    results.append(dict(row))

        return results

    def get_knowledge_by_title(self, category: str, title: str) -> dict | None:
        """Retrieve a specific piece of knowledge by exact title and category."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT category, title, content, tags FROM knowledge WHERE category = ? AND title = ?",
                (category, title)
            )
            row = cur.fetchone()
            return dict(row) if row else None


# Global memory instance
memory_db = MemoryDB()
