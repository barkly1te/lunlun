from __future__ import annotations

import json
import sqlite3
from typing import Any

from database import DB_PATH

from .model import normalize_document, now_iso, new_id


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    conn.execute('PRAGMA foreign_keys=ON;')
    return conn


def create_document_record(
    document: dict[str, Any],
    source_type: str = 'manual',
    source_filename: str | None = None,
    assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_document(document)
    document_id = new_id('doc')
    version_id = new_id('ver')
    timestamp = now_iso()
    payload = json.dumps(normalized, ensure_ascii=False)
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO canvas_documents (
                id, title, document_json, current_version_id,
                source_type, source_filename, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                normalized['title'],
                payload,
                version_id,
                source_type,
                source_filename,
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """
            INSERT INTO canvas_versions (
                id, document_id, version_number, document_json,
                source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_id, document_id, 1, payload, 'initial_import', timestamp),
        )
        for asset in assets or []:
            conn.execute(
                """
                INSERT INTO canvas_assets (
                    id, document_id, filename, mime_type, content,
                    metadata, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset['id'],
                    document_id,
                    asset.get('filename') or asset['id'],
                    asset.get('mime_type') or 'application/octet-stream',
                    asset.get('content') or b'',
                    json.dumps(asset.get('metadata') or {}, ensure_ascii=False),
                    timestamp,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return get_document_record(document_id)


def list_documents() -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT
                d.id,
                d.title,
                d.source_type,
                d.source_filename,
                d.created_at,
                d.updated_at,
                v.version_number,
                d.document_json
            FROM canvas_documents d
            LEFT JOIN canvas_versions v ON v.id = d.current_version_id
            WHERE d.deleted_at IS NULL
            ORDER BY d.updated_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    documents = []
    for row in rows:
        try:
            document = json.loads(row['document_json'])
            block_count = len(document.get('blocks') or [])
        except Exception:
            block_count = 0
        documents.append(
            {
                'id': row['id'],
                'title': row['title'],
                'source_type': row['source_type'],
                'source_filename': row['source_filename'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'version_number': row['version_number'] or 1,
                'block_count': block_count,
            }
        )
    return documents


def get_document_record(document_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT
                d.*,
                v.version_number AS current_version_number
            FROM canvas_documents d
            LEFT JOIN canvas_versions v ON v.id = d.current_version_id
            WHERE d.id = ? AND d.deleted_at IS NULL
            """,
            (document_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f'Canvas document not found: {document_id}')
        asset_rows = conn.execute(
            """
            SELECT id, filename, mime_type, metadata, created_at
            FROM canvas_assets
            WHERE document_id = ?
            ORDER BY created_at ASC
            """,
            (document_id,),
        ).fetchall()
    finally:
        conn.close()

    document = json.loads(row['document_json'])
    return {
        'id': row['id'],
        'title': row['title'],
        'document': document,
        'source_type': row['source_type'],
        'source_filename': row['source_filename'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'current_version_id': row['current_version_id'],
        'current_version_number': row['current_version_number'] or 1,
        'assets': [
            {
                'id': asset['id'],
                'filename': asset['filename'],
                'mime_type': asset['mime_type'],
                'metadata': json.loads(asset['metadata'] or '{}'),
                'created_at': asset['created_at'],
            }
            for asset in asset_rows
        ],
    }


def delete_document_record(document_id: str) -> dict[str, Any]:
    timestamp = now_iso()
    conn = connect()
    try:
        cursor = conn.execute(
            """
            UPDATE canvas_documents
            SET deleted_at = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (timestamp, timestamp, document_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(f'Canvas document not found: {document_id}')
        conn.commit()
    finally:
        conn.close()
    return {'id': document_id, 'deleted': True, 'deleted_at': timestamp}


def save_document_record(
    document_id: str,
    document: dict[str, Any],
    source: str = 'manual_save',
    instruction: str | None = None,
    block_id: str | None = None,
    before_json: dict[str, Any] | None = None,
    after_json: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_document(document)
    timestamp = now_iso()
    payload = json.dumps(normalized, ensure_ascii=False)
    version_id = new_id('ver')
    event_id = new_id('evt')
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) AS max_version
            FROM canvas_versions
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()
        version_number = int(row['max_version'] or 0) + 1
        updated = conn.execute(
            """
            UPDATE canvas_documents
            SET title = ?, document_json = ?, current_version_id = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (normalized['title'], payload, version_id, timestamp, document_id),
        )
        if updated.rowcount == 0:
            raise KeyError(f'Canvas document not found: {document_id}')
        conn.execute(
            """
            INSERT INTO canvas_versions (
                id, document_id, version_number, document_json,
                source, event_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (version_id, document_id, version_number, payload, source, event_id, timestamp),
        )
        conn.execute(
            """
            INSERT INTO canvas_edit_events (
                id, document_id, version_id, event_type, block_id,
                instruction, before_json, after_json, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                document_id,
                version_id,
                source,
                block_id,
                instruction,
                json.dumps(before_json, ensure_ascii=False) if before_json is not None else None,
                json.dumps(after_json, ensure_ascii=False) if after_json is not None else None,
                json.dumps(metadata or {}, ensure_ascii=False),
                timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_document_record(document_id)


def list_versions(document_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT id, version_number, source, event_id, created_at
            FROM canvas_versions
            WHERE document_id = ?
            ORDER BY version_number DESC
            """,
            (document_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def restore_version(document_id: str, version_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT document_json, version_number
            FROM canvas_versions
            WHERE document_id = ? AND id = ?
            """,
            (document_id, version_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise KeyError(f'Canvas version not found: {version_id}')
    document = json.loads(row['document_json'])
    return save_document_record(
        document_id,
        document,
        source='restore_version',
        metadata={'restored_version_id': version_id, 'restored_version_number': row['version_number']},
    )


def restore_previous_version(document_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id
            FROM canvas_versions
            WHERE document_id = ?
            ORDER BY version_number DESC
            LIMIT 1 OFFSET 1
            """,
            (document_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise KeyError('No previous Canvas version exists.')
    return restore_version(document_id, row['id'])



def _message_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'id': row['id'],
        'conversation_id': row['conversation_id'],
        'document_id': row['document_id'],
        'role': row['role'],
        'content': row['content'],
        'command': row['command'],
        'selection': json.loads(row['selection_json'] or '{}'),
        'response': json.loads(row['response_json'] or '{}'),
        'created_at': row['created_at'],
    }


def get_or_create_conversation(
    document_id: str,
    thread_id: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    conn = connect()
    try:
        document_row = conn.execute(
            'SELECT id, title FROM canvas_documents WHERE id = ? AND deleted_at IS NULL',
            (document_id,),
        ).fetchone()
        if document_row is None:
            raise KeyError(f'Canvas document not found: {document_id}')

        if thread_id:
            row = conn.execute(
                """
                SELECT * FROM canvas_conversations
                WHERE document_id = ? AND thread_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (document_id, thread_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM canvas_conversations
                WHERE document_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            conversation_id = new_id('cvs_chat')
            conn.execute(
                """
                INSERT INTO canvas_conversations (
                    id, document_id, thread_id, title, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    document_id,
                    thread_id,
                    f'{document_row["title"]} Canvas Chat',
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            row = conn.execute(
                'SELECT * FROM canvas_conversations WHERE id = ?',
                (conversation_id,),
            ).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_canvas_messages(
    document_id: str,
    thread_id: str | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    conversation = get_or_create_conversation(document_id, thread_id)
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM canvas_messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (conversation['id'], limit),
        ).fetchall()
    finally:
        conn.close()
    return [_message_from_row(row) for row in reversed(rows)]


def append_canvas_message(
    document_id: str,
    role: str,
    content: str,
    *,
    conversation_id: str | None = None,
    thread_id: str | None = None,
    command: str | None = None,
    selection: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    conversation = {'id': conversation_id} if conversation_id else get_or_create_conversation(document_id, thread_id)
    message_id = new_id('cvs_msg')
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO canvas_messages (
                id, conversation_id, document_id, role, content, command,
                selection_json, response_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation['id'],
                document_id,
                role,
                content,
                command,
                json.dumps(selection or {}, ensure_ascii=False),
                json.dumps(response or {}, ensure_ascii=False),
                timestamp,
            ),
        )
        conn.execute(
            'UPDATE canvas_conversations SET updated_at = ? WHERE id = ?',
            (timestamp, conversation['id']),
        )
        conn.commit()
        row = conn.execute(
            'SELECT * FROM canvas_messages WHERE id = ?',
            (message_id,),
        ).fetchone()
        return _message_from_row(row)
    finally:
        conn.close()



def update_canvas_message_response(
    document_id: str,
    message_id: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    timestamp = now_iso()
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT conversation_id
            FROM canvas_messages
            WHERE id = ? AND document_id = ?
            """,
            (message_id, document_id),
        ).fetchone()
        if row is None:
            raise KeyError(f'Canvas message not found: {message_id}')
        conn.execute(
            """
            UPDATE canvas_messages
            SET response_json = ?
            WHERE id = ? AND document_id = ?
            """,
            (json.dumps(response or {}, ensure_ascii=False), message_id, document_id),
        )
        conn.execute(
            'UPDATE canvas_conversations SET updated_at = ? WHERE id = ?',
            (timestamp, row['conversation_id']),
        )
        conn.commit()
        updated = conn.execute(
            'SELECT * FROM canvas_messages WHERE id = ?',
            (message_id,),
        ).fetchone()
        return _message_from_row(updated)
    finally:
        conn.close()


def get_asset(asset_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id, document_id, filename, mime_type, content, metadata, created_at
            FROM canvas_assets
            WHERE id = ?
            """,
            (asset_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise KeyError(f'Canvas asset not found: {asset_id}')
    return {
        'id': row['id'],
        'document_id': row['document_id'],
        'filename': row['filename'],
        'mime_type': row['mime_type'],
        'content': row['content'],
        'metadata': json.loads(row['metadata'] or '{}'),
        'created_at': row['created_at'],
    }

