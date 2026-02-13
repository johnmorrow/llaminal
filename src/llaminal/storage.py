"""SQLite-backed conversation persistence."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "llaminal" / "history.db"


class Storage:
    """Stores conversation sessions and messages in SQLite."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                model TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                role TEXT NOT NULL,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                created_at TEXT NOT NULL
            );
        """)

    def create_session(self, model: str) -> str:
        """Create a new session and return its ID."""
        session_id = uuid.uuid4().hex[:12]
        now = _now()
        self._conn.execute(
            "INSERT INTO sessions (id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, None, model, now, now),
        )
        self._conn.commit()
        return session_id

    def save_messages(self, session_id: str, messages: list[dict], from_index: int) -> None:
        """Persist messages[from_index:] to the database."""
        new_messages = messages[from_index:]
        if not new_messages:
            return

        now = _now()
        rows = []
        title_candidate = None

        for msg in new_messages:
            role = msg["role"]
            content = msg.get("content")
            tool_calls = json.dumps(msg["tool_calls"]) if "tool_calls" in msg else None
            tool_call_id = msg.get("tool_call_id")
            rows.append((session_id, role, content, tool_calls, tool_call_id, now))

            # Auto-title from first user message
            if role == "user" and content and title_candidate is None:
                title_candidate = content[:80]

        self._conn.executemany(
            "INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )

        # Set title if session doesn't have one yet
        if title_candidate:
            self._conn.execute(
                "UPDATE sessions SET title = COALESCE(title, ?), updated_at = ? WHERE id = ?",
                (title_candidate, now, session_id),
            )
        else:
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )

        self._conn.commit()

    def load_session(self, session_id: str) -> list[dict]:
        """Load all messages for a session, returning them in OpenAI format."""
        rows = self._conn.execute(
            "SELECT role, content, tool_calls, tool_call_id FROM messages "
            "WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()

        messages = []
        for row in rows:
            msg: dict = {"role": row["role"]}
            if row["content"] is not None:
                msg["content"] = row["content"]
            if row["tool_calls"] is not None:
                msg["tool_calls"] = json.loads(row["tool_calls"])
            if row["tool_call_id"] is not None:
                msg["tool_call_id"] = row["tool_call_id"]
            messages.append(msg)

        return messages

    def get_latest_session_id(self) -> str | None:
        """Return the most recent session ID, or None."""
        row = self._conn.execute(
            "SELECT id FROM sessions ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """Return recent sessions as dicts with id, title, model, created_at, message_count."""
        rows = self._conn.execute(
            "SELECT s.id, s.title, s.model, s.created_at, s.updated_at, "
            "  (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id AND m.role != 'system') as message_count "
            "FROM sessions s "
            "ORDER BY s.updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [
            {
                "id": r["id"],
                "title": r["title"] or "(untitled)",
                "model": r["model"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "message_count": r["message_count"],
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
