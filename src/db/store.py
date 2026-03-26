from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Iterator

from src.models.job import Job

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    guid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    organisation TEXT NOT NULL,
    description TEXT,
    source_name TEXT NOT NULL,
    country TEXT NOT NULL,
    category TEXT NOT NULL,
    location TEXT,
    closing_date TEXT,
    date_scraped TEXT NOT NULL,
    date_first_seen TEXT NOT NULL,
    date_last_seen TEXT NOT NULL,
    language TEXT DEFAULT 'en',
    is_active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_country_category ON jobs(country, category);
CREATE INDEX IF NOT EXISTS idx_active ON jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_last_seen ON jobs(date_last_seen);

CREATE TABLE IF NOT EXISTS page_hashes (
    source_name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    last_checked TEXT NOT NULL
);
"""


class JobStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_jobs(self, jobs: list[Job]) -> int:
        """Insert or update jobs. Returns count of genuinely new jobs."""
        now = datetime.now(timezone.utc).isoformat()
        new_count = 0

        for job in jobs:
            # Primary dedup: by URL/guid
            existing = self._conn.execute(
                "SELECT guid FROM jobs WHERE guid = ?", (job.guid,)
            ).fetchone()

            if existing:
                self._conn.execute(
                    "UPDATE jobs SET date_last_seen = ?, is_active = 1 WHERE guid = ?",
                    (now, job.guid),
                )
                continue

            # Secondary dedup: title + organisation + source_name match
            dupe = self._conn.execute(
                """SELECT guid FROM jobs
                   WHERE title = ? AND organisation = ? AND source_name = ? AND is_active = 1""",
                (job.title, job.organisation, job.source_name),
            ).fetchone()

            if dupe:
                self._conn.execute(
                    "UPDATE jobs SET date_last_seen = ?, url = ?, guid = ? WHERE guid = ?",
                    (now, job.url, job.guid, dupe["guid"]),
                )
                continue

            # New job
            self._conn.execute(
                """INSERT INTO jobs
                   (guid, title, url, organisation, description, source_name,
                    country, category, location, closing_date, date_scraped,
                    date_first_seen, date_last_seen, language, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    job.guid,
                    job.title,
                    job.url,
                    job.organisation,
                    job.description[:500] if job.description else None,
                    job.source_name,
                    job.country,
                    job.category,
                    job.location,
                    job.closing_date,
                    job.date_scraped,
                    now,
                    now,
                    job.language,
                ),
            )
            new_count += 1

        self._conn.commit()
        return new_count

    def mark_stale(self, days: int = 30) -> int:
        """Mark jobs not seen in `days` days as inactive."""
        cutoff = datetime.now(timezone.utc).replace(microsecond=0)
        cutoff_str = cutoff.isoformat()
        cur = self._conn.execute(
            """UPDATE jobs SET is_active = 0
               WHERE is_active = 1
               AND date_last_seen < datetime(?, ?, ?)""",
            (cutoff_str, "-", f"{days} days"),
        )
        self._conn.commit()
        return cur.rowcount

    def purge_old(self, days: int = 90) -> int:
        """Delete jobs not seen in `days` days."""
        cutoff_str = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "DELETE FROM jobs WHERE date_last_seen < datetime(?, ?, ?)",
            (cutoff_str, "-", f"{days} days"),
        )
        self._conn.commit()
        return cur.rowcount

    def get_active_jobs(self, country: str = "uk") -> list[Job]:
        rows = self._conn.execute(
            """SELECT * FROM jobs WHERE is_active = 1 AND country = ?
               ORDER BY date_first_seen DESC""",
            (country,),
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def get_page_hash(self, source_name: str) -> str | None:
        row = self._conn.execute(
            "SELECT content_hash FROM page_hashes WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        return row["content_hash"] if row else None

    def set_page_hash(self, source_name: str, url: str, content_hash: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO page_hashes (source_name, url, content_hash, last_checked)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source_name) DO UPDATE SET
                 url = excluded.url,
                 content_hash = excluded.content_hash,
                 last_checked = excluded.last_checked""",
            (source_name, url, content_hash, now),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            title=row["title"],
            url=row["url"],
            organisation=row["organisation"],
            description=row["description"] or "",
            source_name=row["source_name"],
            country=row["country"],
            category=row["category"],
            location=row["location"],
            closing_date=row["closing_date"],
            date_scraped=row["date_scraped"],
            language=row["language"] or "en",
        )

    def stats(self) -> dict:
        row = self._conn.execute(
            "SELECT COUNT(*) as total, SUM(is_active) as active FROM jobs"
        ).fetchone()
        return {"total": row["total"], "active": row["active"] or 0}
