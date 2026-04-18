"""
Session Store Module
Provides persistent conversation memory for the Architect-Engineer framework.
Each session stores a list of (task, summary) turns as a JSON file on disk.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SessionStore:
    """
    File-based session storage.

    Each session is saved as a JSON file:
        <storage_dir>/<session_id>.json

    File structure:
    {
        "session_id": "uuid",
        "created_at": "ISO-8601",
        "updated_at": "ISO-8601",
        "turns": [
            {
                "turn": 1,
                "timestamp": "ISO-8601",
                "task": "user task text",
                "summary": "system summary text"
            },
            ...
        ]
    }
    """

    def __init__(self, memory_config: dict):
        raw_dir = memory_config.get("storage_dir", "~/.ollama_ams/sessions")
        self.storage_dir = Path(os.path.expanduser(raw_dir))
        self.max_sessions = int(memory_config.get("max_sessions", 50))
        self.session_ttl_hours = int(memory_config.get("session_ttl_hours", 72))

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("SessionStore initialized at %s", self.storage_dir)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def create_session(self) -> str:
        """Create a new empty session and return its ID."""
        session_id = str(uuid.uuid4())
        data = self._empty_session(session_id)
        self._write(session_id, data)
        logger.debug("Created session %s", session_id)
        return session_id

    def append(self, session_id: str, task: str, summary: str) -> None:
        """
        Append a new (task, summary) turn to the session.
        Creates the session file if it doesn't exist yet.
        """
        data = self._read(session_id)
        if data is None:
            data = self._empty_session(session_id)

        turn_number = len(data["turns"]) + 1
        data["turns"].append({
            "turn": turn_number,
            "timestamp": _now_iso(),
            "task": task,
            "summary": summary,
        })
        data["updated_at"] = _now_iso()

        self._write(session_id, data)
        logger.debug("Session %s: appended turn %d", session_id, turn_number)

        # Housekeeping: prune old sessions
        self._prune_old_sessions()

    def get_history(self, session_id: str) -> list[dict]:
        """
        Return the list of turn dicts for a session.
        Returns an empty list if the session does not exist.
        """
        data = self._read(session_id)
        if data is None:
            return []
        return data.get("turns", [])

    def get_session_ids(self) -> list[str]:
        """Return all session IDs currently stored on disk."""
        return [p.stem for p in self.storage_dir.glob("*.json")]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session file. Returns True if deleted, False if not found."""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            logger.debug("Deleted session %s", session_id)
            return True
        return False

    def list_sessions(self) -> list[dict]:
        """
        Return a summary list of all sessions:
        [{"session_id": ..., "created_at": ..., "updated_at": ..., "turns": N}]
        Sorted by updated_at descending (most recent first).
        """
        summaries = []
        for session_id in self.get_session_ids():
            data = self._read(session_id)
            if data:
                summaries.append({
                    "session_id": session_id,
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "turns": len(data.get("turns", [])),
                })

        summaries.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return summaries

    def get_last_session_id(self) -> Optional[str]:
        """Return the most recently updated session ID, or None if no sessions exist."""
        sessions = self.list_sessions()
        if sessions:
            return sessions[0]["session_id"]
        return None

    def export_session(self, session_id: str, output_path: Optional[str] = None) -> str:
        """
        Export a session as a formatted Markdown string.
        Optionally saves to a file if output_path is given.
        Returns the Markdown string.
        """
        data = self._read(session_id)
        if data is None:
            return f"# Session {session_id}\n\n*Session not found.*"

        lines = [
            f"# Session: {session_id}",
            f"- **Created:** {data.get('created_at', 'N/A')}",
            f"- **Last updated:** {data.get('updated_at', 'N/A')}",
            f"- **Total turns:** {len(data.get('turns', []))}",
            "",
        ]

        for turn in data.get("turns", []):
            lines.append(f"## Turn {turn['turn']} — {turn.get('timestamp', '')}")
            lines.append(f"**Usuario:** {turn.get('task', '')}")
            lines.append("")
            lines.append(f"**Sistema:**\n{turn.get('summary', '')}")
            lines.append("")
            lines.append("---")
            lines.append("")

        markdown = "\n".join(lines)

        if output_path:
            Path(output_path).write_text(markdown, encoding="utf-8")
            logger.info("Session %s exported to %s", session_id, output_path)

        return markdown

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _session_path(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.json"

    def _read(self, session_id: str) -> Optional[dict]:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read session %s: %s", session_id, exc)
            return None

    def _write(self, session_id: str, data: dict) -> None:
        path = self._session_path(session_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.error("Could not write session %s: %s", session_id, exc)

    @staticmethod
    def _empty_session(session_id: str) -> dict:
        now = _now_iso()
        return {
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "turns": [],
        }

    def _prune_old_sessions(self) -> None:
        """
        Remove sessions that exceed max_sessions or are older than session_ttl_hours.
        Called automatically after each append.
        """
        sessions = self.list_sessions()

        # Remove by TTL
        if self.session_ttl_hours > 0:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.session_ttl_hours)
            for s in sessions:
                try:
                    updated = datetime.fromisoformat(s["updated_at"])
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=timezone.utc)
                    if updated < cutoff:
                        self.delete_session(s["session_id"])
                        logger.debug("Pruned expired session %s", s["session_id"])
                except (ValueError, KeyError):
                    pass

        # Re-list after TTL pruning and remove oldest if over limit
        sessions = self.list_sessions()
        if len(sessions) > self.max_sessions:
            to_delete = sessions[self.max_sessions:]
            for s in to_delete:
                self.delete_session(s["session_id"])
                logger.debug("Pruned excess session %s", s["session_id"])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
