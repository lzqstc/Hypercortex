from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    template TEXT NOT NULL DEFAULT '',
    team TEXT NOT NULL DEFAULT '',
    visibility TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'file',
    status TEXT NOT NULL DEFAULT 'queued',
    total INTEGER NOT NULL DEFAULT 0,
    processed INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'file',
    filename TEXT NOT NULL,
    stored_path TEXT,
    source_url TEXT,
    mime TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    pages INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page INTEGER,
    section TEXT NOT NULL DEFAULT '',
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunk_vectors (
    chunk_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    embedding BLOB NOT NULL,
    FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    model TEXT NOT NULL DEFAULT '',
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS researches (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    steps_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_job ON documents(job_id);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_vectors_project ON chunk_vectors(project_id);
CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id, created_at DESC);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO projects (id, name, template, team, visibility, created_at) "
                "VALUES ('default', '默认知识库', '产品知识库', '产品与体验中心', '团队可见', ?)",
                (utcnow(),),
            )
            defaults = {
                "autoSync": True,
                "deepSearch": True,
                "citations": True,
            }
            for key, value in defaults.items():
                connection.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, json.dumps(value)),
                )

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def create_project(self, name: str, template: str, team: str, visibility: str) -> dict[str, Any]:
        project_id = f"prj_{uuid.uuid4().hex}"
        created_at = utcnow()
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, template, team, visibility, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, name, template, team, visibility, created_at),
            )
        return {
            "id": project_id,
            "name": name,
            "template": template,
            "team": team,
            "visibility": visibility,
            "createdAt": created_at,
        }

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY created_at DESC"
            ).fetchall()
        return [self._project_row(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._project_row(row) if row else None

    @staticmethod
    def _project_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "template": row["template"],
            "team": row["team"],
            "visibility": row["visibility"],
            "createdAt": row["created_at"],
        }

    # ------------------------------------------------------------------
    # Jobs / documents
    # ------------------------------------------------------------------
    def create_job(
        self,
        project_id: str,
        job_type: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex}"
        created_at = utcnow()
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO jobs (id, project_id, type, status, total, processed, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, 0, ?, ?)",
                (job_id, project_id, job_type, len(documents), created_at, created_at),
            )
            for document in documents:
                connection.execute(
                    "INSERT INTO documents (id, job_id, project_id, kind, filename, stored_path, source_url, "
                    "mime, size, sha256, status, progress, error, pages, chunk_count, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, 0, 0, ?, ?)",
                    (
                        document["id"],
                        job_id,
                        project_id,
                        document.get("kind", "file"),
                        document["filename"],
                        document.get("stored_path"),
                        document.get("source_url"),
                        document.get("mime", ""),
                        int(document.get("size", 0)),
                        document.get("sha256", ""),
                        created_at,
                        created_at,
                    ),
                )
        return self.get_job(job_id) or {}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                return None
            documents = connection.execute(
                "SELECT * FROM documents WHERE job_id = ? ORDER BY created_at ASC", (job_id,)
            ).fetchall()
        return self._job_row(job, documents)

    def list_jobs(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as connection:
            jobs = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            results = []
            for job in jobs:
                documents = connection.execute(
                    "SELECT * FROM documents WHERE job_id = ? ORDER BY created_at ASC", (job["id"],)
                ).fetchall()
                results.append(self._job_row(job, documents))
        return results

    def _job_row(self, job: sqlite3.Row, documents: Iterable[sqlite3.Row]) -> dict[str, Any]:
        files = [
            {
                "id": document["id"],
                "name": document["filename"],
                "size": document["size"],
                "status": document["status"],
                "progress": document["progress"],
                "error": document["error"],
                "pages": document["pages"],
                "chunks": document["chunk_count"],
                "createdAt": document["created_at"],
            }
            for document in documents
        ]
        return {
            "id": job["id"],
            "projectId": job["project_id"],
            "type": job["type"],
            "fileCount": job["total"],
            "total": job["total"],
            "status": job["status"],
            "processed": job["processed"],
            "error": job["error"],
            "files": files,
            "createdAt": job["created_at"],
        }

    def reset_stuck_documents(self) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE documents SET status = 'queued', progress = 0, updated_at = ? "
                "WHERE status = 'processing'",
                (utcnow(),),
            )
            connection.execute(
                "UPDATE jobs SET status = 'queued', updated_at = ? WHERE status = 'processing'",
                (utcnow(),),
            )

    def claim_next_document(self) -> dict[str, Any] | None:
        with self._lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM documents WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                connection.rollback()
                return None
            connection.execute(
                "UPDATE documents SET status = 'processing', progress = 2, updated_at = ? WHERE id = ?",
                (utcnow(), row["id"]),
            )
            result = dict(row)
            result["status"] = "processing"
            result["progress"] = 2
            return result

    def update_document(self, document_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = utcnow()
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [document_id]
        with self._lock, self.connect() as connection:
            connection.execute(f"UPDATE documents SET {columns} WHERE id = ?", values)

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = utcnow()
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [job_id]
        with self._lock, self.connect() as connection:
            connection.execute(f"UPDATE jobs SET {columns} WHERE id = ?", values)

    def refresh_job_status(self, job_id: str) -> None:
        with self._lock, self.connect() as connection:
            rows = connection.execute(
                "SELECT status FROM documents WHERE job_id = ?", (job_id,)
            ).fetchall()
            statuses = [row["status"] for row in rows]
            processed = sum(
                1 for status in statuses if status in {"completed", "failed", "duplicate"}
            )
            if any(status in {"queued", "processing"} for status in statuses):
                status = "processing" if any(s == "processing" for s in statuses) else "queued"
            elif statuses and all(status == "completed" for status in statuses):
                status = "completed"
            elif statuses and all(status in {"failed", "duplicate"} for status in statuses):
                status = "failed"
            else:
                status = "partial"
            connection.execute(
                "UPDATE jobs SET status = ?, processed = ?, updated_at = ? WHERE id = ?",
                (status, processed, utcnow(), job_id),
            )

    def find_document_by_hash(
        self, project_id: str, sha256: str, exclude_id: str | None = None
    ) -> dict[str, Any] | None:
        if not sha256:
            return None
        query = "SELECT * FROM documents WHERE project_id = ? AND sha256 = ? AND status = 'completed'"
        params: list[Any] = [project_id, sha256]
        if exclude_id:
            query += " AND id != ?"
            params.append(exclude_id)
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return dict(row) if row else None

    def list_documents(self, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM documents"
        params: list[Any] = []
        if project_id:
            query += " WHERE project_id = ?"
            params.append(project_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_document(self, document_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    # ------------------------------------------------------------------
    # Chunks / vectors
    # ------------------------------------------------------------------
    def insert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        with self._lock, self.connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO chunks "
                "(id, document_id, project_id, chunk_index, content, page, section, token_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        chunk["id"],
                        chunk["document_id"],
                        chunk["project_id"],
                        chunk["chunk_index"],
                        chunk["content"],
                        chunk.get("page"),
                        chunk.get("section", ""),
                        int(chunk.get("token_count", 0)),
                        utcnow(),
                    )
                    for chunk in chunks
                ],
            )

    def delete_chunks_for_document(self, document_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT c.*, d.filename, d.source_url FROM chunks c "
                f"JOIN documents d ON d.id = c.document_id "
                f"WHERE c.id IN ({placeholders})",
                chunk_ids,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_chunks_for_project(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT c.*, d.filename FROM chunks c "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE c.project_id = ? ORDER BY c.document_id, c.chunk_index",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_chunks(self, project_id: str | None = None) -> int:
        query = "SELECT COUNT(*) AS count FROM chunks"
        params: list[Any] = []
        if project_id:
            query += " WHERE project_id = ?"
            params.append(project_id)
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row["count"]) if row else 0

    def count_documents(self, project_id: str | None = None) -> int:
        query = "SELECT COUNT(*) AS count FROM documents"
        params: list[Any] = []
        if project_id:
            query += " WHERE project_id = ?"
            params.append(project_id)
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row["count"]) if row else 0

    def store_vectors(self, vectors: list[tuple[str, str, str, bytes]]) -> None:
        if not vectors:
            return
        with self._lock, self.connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO chunk_vectors (chunk_id, project_id, document_id, embedding) "
                "VALUES (?, ?, ?, ?)",
                vectors,
            )

    def get_vectors_for_project(self, project_id: str) -> list[tuple[str, bytes]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT chunk_id, embedding FROM chunk_vectors WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [(row["chunk_id"], row["embedding"]) for row in rows]

    def delete_vectors_for_document(self, document_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "DELETE FROM chunk_vectors WHERE document_id = ?", (document_id,)
            )

    # ------------------------------------------------------------------
    # Conversations / research
    # ------------------------------------------------------------------
    def create_conversation(
        self,
        project_id: str,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
        model: str,
        latency_ms: int,
    ) -> dict[str, Any]:
        conversation_id = f"conv_{uuid.uuid4().hex}"
        created_at = utcnow()
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO conversations "
                "(id, project_id, question, answer, sources_json, model, latency_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    project_id,
                    question,
                    answer,
                    json.dumps(sources, ensure_ascii=False),
                    model,
                    latency_ms,
                    created_at,
                ),
            )
        return {
            "id": conversation_id,
            "question": question,
            "answer": answer,
            "sources": sources,
            "model": model,
            "latencyMs": latency_ms,
            "createdAt": created_at,
        }

    def list_conversations(self, project_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        query = "SELECT * FROM conversations"
        params: list[Any] = []
        if project_id:
            query += " WHERE project_id = ?"
            params.append(project_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "projectId": row["project_id"],
                "question": row["question"],
                "answer": row["answer"],
                "sources": json.loads(row["sources_json"] or "[]"),
                "model": row["model"],
                "latencyMs": row["latency_ms"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def create_research(self, project_id: str, topic: str) -> dict[str, Any]:
        research_id = f"res_{uuid.uuid4().hex}"
        created_at = utcnow()
        steps = ["拆解研究主题", "检索并聚类证据", "交叉验证矛盾点", "生成结构化结论", "输出 wiki 卡片"]
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO researches (id, project_id, topic, status, steps_json, created_at) "
                "VALUES (?, ?, ?, 'running', ?, ?)",
                (research_id, project_id, topic, json.dumps(steps, ensure_ascii=False), created_at),
            )
        return {
            "id": research_id,
            "topic": topic,
            "status": "running",
            "steps": steps,
            "createdAt": created_at,
        }

    def list_researches(self, project_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        query = "SELECT * FROM researches"
        params: list[Any] = []
        if project_id:
            query += " WHERE project_id = ?"
            params.append(project_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "topic": row["topic"],
                "status": row["status"],
                "steps": json.loads(row["steps_json"] or "[]"),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Notifications / settings
    # ------------------------------------------------------------------
    def add_notification(self, title: str, detail: str = "") -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO notifications (id, title, detail, read, created_at) VALUES (?, ?, ?, 0, ?)",
                (f"ntf_{uuid.uuid4().hex}", title, detail, utcnow()),
            )

    def list_notifications(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "detail": row["detail"],
                "read": bool(row["read"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def get_settings(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            for key, value in updates.items():
                connection.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)),
                )
        return self.get_settings()
