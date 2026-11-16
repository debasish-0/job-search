from __future__ import annotations

import json
from pathlib import Path

from ..models import Job


class LocalJsonCollector:
    name = "local_json"

    def __init__(self, path: str | Path, company: str = "") -> None:
        self.path = Path(path)
        self.company = company

    def collect(self) -> list[Job]:
        if not self.path.exists():
            raise RuntimeError(f"Local job file not found: {self.path}")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {self.path}: {exc}") from exc
        if isinstance(payload, dict):
            payload = payload.get("jobs", [])
        if not isinstance(payload, list):
            raise RuntimeError(f"Expected a JSON array in {self.path}")
        jobs: list[Job] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            jobs.append(
                Job(
                    source=self.name,
                    source_job_id=str(item.get("id") or item.get("source_job_id") or index),
                    company=str(item.get("company") or self.company or "Unknown company"),
                    title=str(item.get("title") or "Untitled role"),
                    location=str(item.get("location") or ""),
                    workplace_type=str(item.get("workplace_type") or ""),
                    description=str(item.get("description") or ""),
                    job_url=str(item.get("job_url") or item.get("url") or ""),
                    apply_url=str(
                        item.get("apply_url")
                        or item.get("job_url")
                        or item.get("url")
                        or ""
                    ),
                    department=str(item.get("department") or ""),
                    employment_type=str(item.get("employment_type") or ""),
                    salary_text=str(item.get("salary_text") or ""),
                    posted_at=str(item.get("posted_at") or ""),
                ).finalize()
            )
        return jobs
