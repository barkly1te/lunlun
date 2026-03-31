import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

DB_PATH = 'lunlun_history.db'


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    return conn


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def init_sqlite_db():
    """Create the tables needed by Chainlit plus local agent-state storage."""
    conn = _connect()
    cursor = conn.cursor()

    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            "id" TEXT PRIMARY KEY,
            "identifier" TEXT NOT NULL UNIQUE,
            "metadata" TEXT NOT NULL,
            "createdAt" TEXT
        );
        CREATE TABLE IF NOT EXISTS threads (
            "id" TEXT PRIMARY KEY,
            "createdAt" TEXT,
            "name" TEXT,
            "userId" TEXT,
            "userIdentifier" TEXT,
            "tags" TEXT,
            "metadata" TEXT,
            FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS steps (
            "id" TEXT PRIMARY KEY,
            "name" TEXT NOT NULL,
            "type" TEXT NOT NULL,
            "threadId" TEXT NOT NULL,
            "parentId" TEXT,
            "disableFeedback" INTEGER NOT NULL DEFAULT 0,
            "streaming" INTEGER NOT NULL,
            "waitForAnswer" INTEGER,
            "isError" INTEGER,
            "metadata" TEXT,
            "tags" TEXT,
            "input" TEXT,
            "output" TEXT,
            "createdAt" TEXT,
            "command" TEXT,
            "start" TEXT,
            "end" TEXT,
            "generation" TEXT,
            "showInput" TEXT,
            "language" TEXT,
            "indent" INTEGER,
            "defaultOpen" INTEGER,
            "autoCollapse" INTEGER,
            FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS elements (
            "id" TEXT PRIMARY KEY,
            "threadId" TEXT,
            "type" TEXT,
            "url" TEXT,
            "chainlitKey" TEXT,
            "name" TEXT NOT NULL,
            "display" TEXT,
            "objectKey" TEXT,
            "size" TEXT,
            "page" INTEGER,
            "language" TEXT,
            "forId" TEXT,
            "mime" TEXT,
            "props" TEXT,
            FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS feedbacks (
            "id" TEXT PRIMARY KEY,
            "forId" TEXT NOT NULL,
            "threadId" TEXT NOT NULL,
            "value" INTEGER NOT NULL,
            "comment" TEXT,
            FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS agent_states (
            "threadId" TEXT PRIMARY KEY,
            "state" TEXT NOT NULL,
            "updatedAt" TEXT,
            FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    conn.close()


def save_agent_state(thread_id: str, state: dict[str, Any]) -> None:
    """Persist the serialized AgentScope state for a thread."""
    conn = _connect()
    conn.execute(
        """
        INSERT INTO agent_states ("threadId", "state", "updatedAt")
        VALUES (?, ?, ?)
        ON CONFLICT ("threadId") DO UPDATE SET
            "state" = excluded."state",
            "updatedAt" = excluded."updatedAt"
        """,
        (thread_id, json.dumps(state, ensure_ascii=False), _now_iso()),
    )
    conn.commit()
    conn.close()


def load_agent_state(thread_id: str) -> dict[str, Any] | None:
    """Load the serialized AgentScope state for a thread if it exists."""
    conn = _connect()
    row = conn.execute(
        'SELECT "state" FROM agent_states WHERE "threadId" = ?',
        (thread_id,),
    ).fetchone()
    conn.close()

    if row is None:
        return None

    raw_state = row['state']
    if not raw_state:
        return None

    return json.loads(raw_state)
