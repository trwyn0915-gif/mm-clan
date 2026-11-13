"""Small local SQLite memory store for MM Commander; Python standard library only."""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("MM_MEMORY_DB", "mm_commander_memory.sqlite3"))

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def initialize() -> None:
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL CHECK(role IN ('member','assistant')),
            body TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_time ON messages(chat_id, created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_time ON messages(chat_id, user_id, created_at)")
        db.execute("""CREATE TABLE IF NOT EXISTS member_notes (
            chat_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            note TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(chat_id, user_id, note)
        )""")

def save_message(chat_id: str, user_id: str, display_name: str, role: str, body: str) -> None:
    body = (body or "").strip()[:3000]
    if not chat_id or not user_id or not body or role not in {"member", "assistant"}:
        return
    with _connect() as db:
        db.execute(
            "INSERT INTO messages(chat_id,user_id,display_name,role,body,created_at) VALUES(?,?,?,?,?,?)",
            (str(chat_id), str(user_id), (display_name or "")[:100], role, body, int(time.time())),
        )

def recent_messages(chat_id: str, limit: int = 12) -> list[tuple[str, str]]:
    limit = max(1, min(int(limit), 30))
    with _connect() as db:
        rows = db.execute(
            "SELECT display_name, body FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (str(chat_id), limit),
        ).fetchall()
    return [(name or "عضو", body) for name, body in reversed(rows)]

def remember_member_note(chat_id: str, user_id: str, note: str) -> None:
    note = (note or "").strip()[:500]
    if not chat_id or not user_id or not note:
        return
    with _connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO member_notes(chat_id,user_id,note,updated_at) VALUES(?,?,?,?)",
            (str(chat_id), str(user_id), note, int(time.time())),
        )

def member_notes(chat_id: str, user_id: str, limit: int = 20) -> list[str]:
    with _connect() as db:
        rows = db.execute(
            "SELECT note FROM member_notes WHERE chat_id=? AND user_id=? ORDER BY updated_at DESC LIMIT ?",
            (str(chat_id), str(user_id), max(1, min(int(limit), 50))),
        ).fetchall()
    return [row[0] for row in rows]

def forget_member(chat_id: str, user_id: str) -> None:
    """Delete stored conversation and notes for one member in one chat."""
    with _connect() as db:
        db.execute("DELETE FROM messages WHERE chat_id=? AND user_id=?", (str(chat_id), str(user_id)))
        db.execute("DELETE FROM member_notes WHERE chat_id=? AND user_id=?", (str(chat_id), str(user_id)))

def clear_chat(chat_id: str) -> None:
    with _connect() as db:
        db.execute("DELETE FROM messages WHERE chat_id=?", (str(chat_id),))
        db.execute("DELETE FROM member_notes WHERE chat_id=?", (str(chat_id),))
