"""SQLite 读写：只做幂等写入与最小查询。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))


def upsert_conversation(conn: sqlite3.Connection, rec: dict) -> None:
    conn.execute(
        """INSERT INTO conversations(conv_id, conv_type, conv_name, updated_at)
           VALUES (?,?,?,?)
           ON CONFLICT(conv_id) DO UPDATE SET
             conv_type=excluded.conv_type,
             conv_name=CASE WHEN excluded.conv_name<>'' THEN excluded.conv_name ELSE conversations.conv_name END,
             updated_at=excluded.updated_at""",
        (rec["conv_id"], rec["conv_type"], rec.get("conv_name", ""),
         rec["sent_at"]),
    )


def insert_message(conn: sqlite3.Connection, rec: dict) -> bool:
    """插入一条消息；重复（dedup_hash 冲突）返回 False。"""
    try:
        conn.execute(
            """INSERT INTO messages(msg_id, conv_id, sender_id, sender_name, sent_at,
                                    msg_type, text, raw_json, dedup_hash, ingested_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (rec["msg_id"], rec["conv_id"], rec["sender_id"], rec["sender_name"],
             rec["sent_at"], rec["msg_type"], rec["text"], rec["raw_json"],
             rec["dedup_hash"], datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def set_cursor(conn: sqlite3.Connection, source: str, cursor: str | None,
               error: str | None = None) -> None:
    conn.execute(
        """INSERT INTO sync_state(source, cursor, last_run_at, last_error)
           VALUES (?,?,?,?)
           ON CONFLICT(source) DO UPDATE SET
             cursor=COALESCE(excluded.cursor, sync_state.cursor),
             last_run_at=excluded.last_run_at,
             last_error=excluded.last_error""",
        (source, cursor, datetime.now(timezone.utc).isoformat(timespec="seconds"), error),
    )


def stats(conn: sqlite3.Connection) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "conversations": q("SELECT COUNT(*) FROM conversations"),
        "messages": q("SELECT COUNT(*) FROM messages"),
        "attachments": q("SELECT COUNT(*) FROM attachments"),
        "latest": q("SELECT COALESCE(MAX(sent_at), '-') FROM messages"),
    }


def search(conn: sqlite3.Connection, kw: str, limit: int = 20) -> list[sqlite3.Row]:
    """trigram 只支持 >=3 字符；更短的词用 LIKE 兜底。"""
    if len(kw) >= 3:
        return conn.execute(
            """SELECT m.msg_id, m.conv_id, c.conv_name, m.sender_name, m.sent_at, m.text
               FROM messages_fts f JOIN messages m ON m.rowid=f.rowid
               LEFT JOIN conversations c ON c.conv_id=m.conv_id
               WHERE messages_fts MATCH ? ORDER BY m.sent_at DESC LIMIT ?""",
            (f'"{kw}"', limit),
        ).fetchall()
    return conn.execute(
        """SELECT m.msg_id, m.conv_id, c.conv_name, m.sender_name, m.sent_at, m.text
           FROM messages m LEFT JOIN conversations c ON c.conv_id=m.conv_id
           WHERE m.text LIKE ? ORDER BY m.sent_at DESC LIMIT ?""",
        (f"%{kw}%", limit),
    ).fetchall()
