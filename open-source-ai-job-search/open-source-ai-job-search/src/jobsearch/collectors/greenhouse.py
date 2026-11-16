from __future__ import annotations

from typing import Any

from ..http import HttpJsonClient
from ..models import Job
from ..text import strip_html


class GreenhouseCollector:
    name = "greenhouse"

    def __init__(
        self,
        board: str,
        company: str,
        client: HttpJsonClient,
    ) -> None:
        self.board = board
        self.company = company
        self.client = client

    def _company_name(self) -> str:
        if self.company:
            return self.company
        try:
            payload = self.client.get_json(
                f"https://boards-api.greenhouse.io/v1/boards/{self.board}"
            )
            if isinstance(payload, dict):
                return str(payload.get("name") or self.board)
        except RuntimeError:
            pass
        return self.board

    def collect(self) -> list[Job]:
        payload = self.client.get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{self.board}/jobs",
            {"content": "true"},
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected Greenhouse response for {self.board}")
        company = self._company_name()
        jobs: list[Job] = []
        for item in payload.get("jobs", []):
            if not isinstance(item, dict):
                continue
            location = item.get("location") or {}
            departments = item.get("departments") or []
            department = ", ".join(
                str(entry.get("name", ""))
                for entry in departments
                if isinstance(entry, dict) and entry.get("name")
            )
            metadata = _metadata_map(item.get("metadata"))
            workplace_type = _metadata_value(
                metadata,
                "workplace type",
                "workplace_type",
                "remote",
            )
            employment_type = _metadata_value(
                metadata,
                "employment type",
                "employment_type",
                "commitment",
            )
            jobs.append(
                Job(
                    source=self.name,
                    source_job_id=str(item.get("id") or ""),
                    company=company,
                    title=str(item.get("title") or "Untitled role"),
                    location=str(
                        location.get("name", "") if isinstance(location, dict) else location
                    ),
                    workplace_type=workplace_type,
                    description=strip_html(str(item.get("content") or "")),
                    job_url=str(item.get("absolute_url") or ""),
                    apply_url=str(item.get("absolute_url") or ""),
                    department=department,
                    employment_type=employment_type,
                    posted_at=str(item.get("updated_at") or ""),
                ).finalize()
            )
        return jobs


def _metadata_map(raw: Any) -> dict[str, str]:
    output: dict[str, str] = {}
    if not isinstance(raw, list):
        return output
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        value = item.get("value")
        if isinstance(value, list):
            text = ", ".join(str(entry) for entry in value)
        else:
            text = str(value or "")
        if name and text:
            output[name] = text
    return output


def _metadata_value(metadata: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key.lower())
        if value:
            return value
    return ""
