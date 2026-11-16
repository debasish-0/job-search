from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .models import Job, MatchResult


VALID_STATUSES = {
    "discovered",
    "shortlisted",
    "approved",
    "applied",
    "interview",
    "rejected",
    "offer",
    "archived",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    stats_json TEXT NOT NULL DEFAULT '{}',
                    error_text TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_job_id TEXT NOT NULL,
                    source_key TEXT NOT NULL UNIQUE,
                    canonical_key TEXT NOT NULL,
                    alternate_sources_json TEXT NOT NULL DEFAULT '[]',
                    alternate_urls_json TEXT NOT NULL DEFAULT '[]',
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    workplace_type TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    job_url TEXT NOT NULL DEFAULT '',
                    apply_url TEXT NOT NULL DEFAULT '',
                    department TEXT NOT NULL DEFAULT '',
                    employment_type TEXT NOT NULL DEFAULT '',
                    salary_text TEXT NOT NULL DEFAULT '',
                    posted_at TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'discovered',
                    score REAL,
                    score_breakdown_json TEXT NOT NULL DEFAULT '{}',
                    analysis_json TEXT NOT NULL DEFAULT '{}',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    score_updated_at TEXT,
                    last_run_id INTEGER,
                    FOREIGN KEY(last_run_id) REFERENCES workflow_runs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_canonical_key
                    ON jobs(canonical_key);
                CREATE INDEX IF NOT EXISTS idx_jobs_score
                    ON jobs(score DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_status
                    ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_last_run
                    ON jobs(last_run_id);

                CREATE TABLE IF NOT EXISTS application_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, kind, path),
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );
                """
            )

    def start_run(self) -> int:
        with self.connection() as connection:
            cursor = connection.execute(
                "INSERT INTO workflow_runs(started_at, status) VALUES (?, ?)",
                (utc_now(), "running"),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        stats: dict[str, Any],
        error_text: str = "",
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE workflow_runs
                SET finished_at = ?, status = ?, stats_json = ?, error_text = ?
                WHERE id = ?
                """,
                (utc_now(), status, json.dumps(stats), error_text, run_id),
            )

    def upsert_job(self, job: Job, run_id: int) -> tuple[int, bool, bool]:
        job.finalize()
        now = utc_now()
        with self.connection() as connection:
            existing = connection.execute(
                "SELECT * FROM jobs WHERE source_key = ?", (job.source_key,)
            ).fetchone()
            if existing is not None:
                changed = existing["content_hash"] != job.content_hash
                self._update_existing(connection, int(existing["id"]), job, run_id, changed, now)
                return int(existing["id"]), False, changed

            canonical = connection.execute(
                """
                SELECT * FROM jobs
                WHERE canonical_key = ? AND is_active = 1
                ORDER BY id ASC LIMIT 1
                """,
                (job.canonical_key,),
            ).fetchone()
            if canonical is not None:
                sources = _json_list(canonical["alternate_sources_json"])
                urls = _json_list(canonical["alternate_urls_json"])
                if job.source not in sources and job.source != canonical["source"]:
                    sources.append(job.source)
                for url in (job.job_url, job.apply_url):
                    if url and url not in urls and url not in {
                        canonical["job_url"],
                        canonical["apply_url"],
                    }:
                        urls.append(url)
                richer = len(job.description) > len(str(canonical["description"]))
                changed = richer or canonical["content_hash"] != job.content_hash
                if richer:
                    self._update_existing(
                        connection,
                        int(canonical["id"]),
                        job,
                        run_id,
                        changed,
                        now,
                        preserve_source=True,
                        alternate_sources=sources,
                        alternate_urls=urls,
                    )
                else:
                    connection.execute(
                        """
                        UPDATE jobs
                        SET alternate_sources_json = ?, alternate_urls_json = ?,
                            last_seen_at = ?, last_run_id = ?, is_active = 1
                        WHERE id = ?
                        """,
                        (
                            json.dumps(sources),
                            json.dumps(urls),
                            now,
                            run_id,
                            int(canonical["id"]),
                        ),
                    )
                return int(canonical["id"]), False, changed

            cursor = connection.execute(
                """
                INSERT INTO jobs(
                    source, source_job_id, source_key, canonical_key,
                    company, title, location, workplace_type, description,
                    job_url, apply_url, department, employment_type, salary_text,
                    posted_at, content_hash, status, first_seen_at, last_seen_at,
                    updated_at, last_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'discovered', ?, ?, ?, ?)
                """,
                (
                    job.source,
                    job.source_job_id,
                    job.source_key,
                    job.canonical_key,
                    job.company,
                    job.title,
                    job.location,
                    job.workplace_type,
                    job.description,
                    job.job_url,
                    job.apply_url,
                    job.department,
                    job.employment_type,
                    job.salary_text,
                    job.posted_at,
                    job.content_hash,
                    now,
                    now,
                    now,
                    run_id,
                ),
            )
            return int(cursor.lastrowid), True, True

    def _update_existing(
        self,
        connection: sqlite3.Connection,
        job_id: int,
        job: Job,
        run_id: int,
        changed: bool,
        now: str,
        preserve_source: bool = False,
        alternate_sources: list[str] | None = None,
        alternate_urls: list[str] | None = None,
    ) -> None:
        score_clause = (
            ", score = NULL, score_breakdown_json = '{}', analysis_json = '{}', "
            "score_updated_at = NULL"
            if changed
            else ""
        )
        source_clause = "" if preserve_source else ", source = ?, source_job_id = ?, source_key = ?"
        parameters: list[Any] = [
            job.canonical_key,
            job.company,
            job.title,
            job.location,
            job.workplace_type,
            job.description,
            job.job_url,
            job.apply_url,
            job.department,
            job.employment_type,
            job.salary_text,
            job.posted_at,
            job.content_hash,
            now,
            now if changed else None,
            run_id,
        ]
        if not changed:
            # Keep the previous updated_at when only last_seen_at changes.
            parameters[14] = self._get_updated_at(connection, job_id)
        if not preserve_source:
            parameters.extend([job.source, job.source_job_id, job.source_key])
        alternate_clause = ""
        if alternate_sources is not None and alternate_urls is not None:
            alternate_clause = ", alternate_sources_json = ?, alternate_urls_json = ?"
            parameters.extend([json.dumps(alternate_sources), json.dumps(alternate_urls)])
        parameters.append(job_id)
        connection.execute(
            f"""
            UPDATE jobs
            SET canonical_key = ?, company = ?, title = ?, location = ?,
                workplace_type = ?, description = ?, job_url = ?, apply_url = ?,
                department = ?, employment_type = ?, salary_text = ?, posted_at = ?,
                content_hash = ?, last_seen_at = ?, updated_at = ?, last_run_id = ?,
                is_active = 1
                {source_clause}
                {alternate_clause}
                {score_clause}
            WHERE id = ?
            """,
            parameters,
        )

    @staticmethod
    def _get_updated_at(connection: sqlite3.Connection, job_id: int) -> str:
        row = connection.execute(
            "SELECT updated_at FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return str(row["updated_at"]) if row else utc_now()

    def jobs_for_scoring(self, job_ids: list[int], rescore: bool = False) -> list[dict[str, Any]]:
        if not job_ids:
            return []
        placeholders = ",".join("?" for _ in job_ids)
        condition = "" if rescore else "AND score IS NULL"
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM jobs
                WHERE id IN ({placeholders}) AND is_active = 1 {condition}
                ORDER BY id ASC
                """,
                job_ids,
            ).fetchall()
        return [_row_to_job_dict(row) for row in rows]

    def save_score(self, job_id: int, result: MatchResult) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET score = ?, score_breakdown_json = ?, score_updated_at = ?
                WHERE id = ?
                """,
                (result.score, json.dumps(result.to_dict()), utc_now(), job_id),
            )

    def save_analysis(self, job_id: int, analysis: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE jobs SET analysis_json = ? WHERE id = ?",
                (json.dumps(analysis), job_id),
            )

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job_dict(row) if row else None

    def list_jobs(
        self,
        minimum_score: float = 0,
        status: str | None = None,
        active_only: bool = True,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses = ["COALESCE(score, 0) >= ?"]
        params: list[Any] = [minimum_score]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if active_only:
            clauses.append("is_active = 1")
        params.append(limit)
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM jobs
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(score, 0) DESC, last_seen_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_row_to_job_dict(row) for row in rows]

    def jobs_by_ids(
        self, job_ids: list[int], minimum_score: float = 0
    ) -> list[dict[str, Any]]:
        if not job_ids:
            return []
        placeholders = ",".join("?" for _ in job_ids)
        params: list[Any] = [*job_ids, minimum_score]
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM jobs
                WHERE id IN ({placeholders})
                  AND COALESCE(score, 0) >= ?
                  AND is_active = 1
                ORDER BY score DESC
                """,
                params,
            ).fetchall()
        return [_row_to_job_dict(row) for row in rows]

    def jobs_from_run(self, run_id: int, minimum_score: float = 0) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs
                WHERE last_run_id = ? AND COALESCE(score, 0) >= ? AND is_active = 1
                ORDER BY score DESC
                """,
                (run_id, minimum_score),
            ).fetchall()
        return [_row_to_job_dict(row) for row in rows]

    def set_status(self, job_id: int, status: str, notes: str = "") -> None:
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Choose from: {', '.join(sorted(VALID_STATUSES))}"
            )
        with self.connection() as connection:
            row = connection.execute(
                "SELECT status FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Job {job_id} not found")
            previous = str(row["status"])
            connection.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), job_id),
            )
            connection.execute(
                """
                INSERT INTO application_events(job_id, from_status, to_status, notes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, previous, status, notes, utc_now()),
            )

    def add_draft(self, job_id: int, kind: str, path: str | Path) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO drafts(job_id, kind, path, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, kind, str(path), utc_now()),
            )

    def get_drafts(self, job_id: int) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM drafts WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_events(self, job_id: int) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM application_events
                WHERE job_id = ? ORDER BY created_at DESC
                """,
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            value = dict(row)
            value["stats"] = _json_dict(value.pop("stats_json", "{}"))
            output.append(value)
        return output

    def metrics(self) -> dict[str, Any]:
        with self.connection() as connection:
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE is_active = 1"
            ).fetchone()["count"]
            strong = connection.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE is_active = 1 AND score >= 75"
            ).fetchone()["count"]
            statuses = connection.execute(
                """
                SELECT status, COUNT(*) AS count FROM jobs
                WHERE is_active = 1 GROUP BY status ORDER BY status
                """
            ).fetchall()
            average = connection.execute(
                "SELECT AVG(score) AS value FROM jobs WHERE is_active = 1 AND score IS NOT NULL"
            ).fetchone()["value"]
        return {
            "active_jobs": int(total),
            "strong_matches": int(strong),
            "average_score": round(float(average or 0), 1),
            "by_status": {str(row["status"]): int(row["count"]) for row in statuses},
        }

    def deactivate_stale(self, days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=max(1, days))).isoformat()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET is_active = 0
                WHERE last_seen_at < ? AND status IN ('discovered', 'shortlisted', 'rejected')
                """,
                (cutoff,),
            )
            return int(cursor.rowcount)


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return [str(item) for item in value] if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def _json_dict(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _row_to_job_dict(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["score_breakdown"] = _json_dict(value.pop("score_breakdown_json", "{}"))
    value["analysis"] = _json_dict(value.pop("analysis_json", "{}"))
    value["alternate_sources"] = _json_list(
        value.pop("alternate_sources_json", "[]")
    )
    value["alternate_urls"] = _json_list(value.pop("alternate_urls_json", "[]"))
    value["is_active"] = bool(value.get("is_active"))
    return value
