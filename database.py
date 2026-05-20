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
        CREATE TABLE IF NOT EXISTS canvas_documents (
            "id" TEXT PRIMARY KEY,
            "title" TEXT NOT NULL,
            "document_json" TEXT NOT NULL,
            "current_version_id" TEXT,
            "source_type" TEXT,
            "source_filename" TEXT,
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL,
            "deleted_at" TEXT
        );
        CREATE TABLE IF NOT EXISTS canvas_versions (
            "id" TEXT PRIMARY KEY,
            "document_id" TEXT NOT NULL,
            "version_number" INTEGER NOT NULL,
            "document_json" TEXT NOT NULL,
            "source" TEXT NOT NULL,
            "event_id" TEXT,
            "created_at" TEXT NOT NULL,
            FOREIGN KEY ("document_id") REFERENCES canvas_documents("id") ON DELETE CASCADE,
            UNIQUE ("document_id", "version_number")
        );
        CREATE TABLE IF NOT EXISTS canvas_assets (
            "id" TEXT PRIMARY KEY,
            "document_id" TEXT NOT NULL,
            "filename" TEXT NOT NULL,
            "mime_type" TEXT NOT NULL,
            "content" BLOB NOT NULL,
            "metadata" TEXT,
            "created_at" TEXT NOT NULL,
            FOREIGN KEY ("document_id") REFERENCES canvas_documents("id") ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS canvas_edit_events (
            "id" TEXT PRIMARY KEY,
            "document_id" TEXT NOT NULL,
            "version_id" TEXT,
            "event_type" TEXT NOT NULL,
            "block_id" TEXT,
            "instruction" TEXT,
            "before_json" TEXT,
            "after_json" TEXT,
            "metadata" TEXT,
            "created_at" TEXT NOT NULL,
            FOREIGN KEY ("document_id") REFERENCES canvas_documents("id") ON DELETE CASCADE,
            FOREIGN KEY ("version_id") REFERENCES canvas_versions("id") ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS canvas_conversations (
            "id" TEXT PRIMARY KEY,
            "document_id" TEXT NOT NULL,
            "thread_id" TEXT,
            "title" TEXT,
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL,
            FOREIGN KEY ("document_id") REFERENCES canvas_documents("id") ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS canvas_messages (
            "id" TEXT PRIMARY KEY,
            "conversation_id" TEXT NOT NULL,
            "document_id" TEXT NOT NULL,
            "role" TEXT NOT NULL,
            "content" TEXT NOT NULL,
            "command" TEXT,
            "selection_json" TEXT,
            "response_json" TEXT,
            "created_at" TEXT NOT NULL,
            FOREIGN KEY ("conversation_id") REFERENCES canvas_conversations("id") ON DELETE CASCADE,
            FOREIGN KEY ("document_id") REFERENCES canvas_documents("id") ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_canvas_documents_updated_at
            ON canvas_documents ("updated_at");
        CREATE INDEX IF NOT EXISTS idx_canvas_versions_document_id
            ON canvas_versions ("document_id", "version_number");
        CREATE INDEX IF NOT EXISTS idx_canvas_assets_document_id
            ON canvas_assets ("document_id");
        CREATE INDEX IF NOT EXISTS idx_canvas_edit_events_document_id
            ON canvas_edit_events ("document_id", "created_at");
        CREATE INDEX IF NOT EXISTS idx_canvas_conversations_document_id
            ON canvas_conversations ("document_id", "updated_at");
        CREATE INDEX IF NOT EXISTS idx_canvas_messages_conversation_id
            ON canvas_messages ("conversation_id", "created_at");
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
