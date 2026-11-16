from __future__ import annotations

from typing import Any

from ..http import HttpJsonClient
from ..models import Job
from ..text import strip_html


class LeverCollector:
    name = "lever"

    def __init__(
        self,
        site: str,
        company: str,
        client: HttpJsonClient,
        region: str = "global",
    ) -> None:
        self.site = site
        self.company = company or site
        self.client = client
        self.region = region.lower()

    def collect(self) -> list[Job]:
        host = "api.eu.lever.co" if self.region == "eu" else "api.lever.co"
        endpoint = f"https://{host}/v0/postings/{self.site}"
        payload: list[Any] = []
        page_size = 100
        skip = 0
        while True:
            page = self.client.get_json(
                endpoint,
                {"mode": "json", "limit": page_size, "skip": skip},
            )
            if not isinstance(page, list):
                raise RuntimeError(f"Unexpected Lever response for {self.site}")
            payload.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
            if skip >= 10000:
                break
        jobs: list[Job] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            categories = item.get("categories") or {}
            if not isinstance(categories, dict):
                categories = {}
            description = str(item.get("descriptionPlain") or "")
            if not description:
                description = _build_description(item)
            salary = _salary_text(item)
            jobs.append(
                Job(
                    source=self.name,
                    source_job_id=str(item.get("id") or ""),
                    company=self.company,
                    title=str(item.get("text") or "Untitled role"),
                    location=str(categories.get("location") or ""),
                    workplace_type=str(item.get("workplaceType") or ""),
                    description=strip_html(description),
                    job_url=str(item.get("hostedUrl") or ""),
                    apply_url=str(item.get("applyUrl") or item.get("hostedUrl") or ""),
                    department=str(categories.get("department") or ""),
                    employment_type=str(categories.get("commitment") or ""),
                    salary_text=salary,
                    posted_at=str(item.get("createdAt") or item.get("updatedAt") or ""),
                ).finalize()
            )
        return jobs


def _build_description(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("openingPlain") or item.get("opening") or ""),
        str(item.get("descriptionBodyPlain") or item.get("descriptionBody") or ""),
    ]
    lists = item.get("lists") or []
    for entry in lists:
        if not isinstance(entry, dict):
            continue
        parts.append(str(entry.get("text") or ""))
        parts.append(strip_html(str(entry.get("content") or "")))
    parts.append(str(item.get("additionalPlain") or item.get("additional") or ""))
    return "\n".join(part for part in parts if part)


def _salary_text(item: dict[str, Any]) -> str:
    plain = str(item.get("salaryDescriptionPlain") or "").strip()
    if plain:
        return plain
    salary = item.get("salaryRange")
    if not isinstance(salary, dict):
        return ""
    minimum = salary.get("min")
    maximum = salary.get("max")
    currency = str(salary.get("currency") or "").strip()
    interval = str(salary.get("interval") or "").strip()
    if minimum is None and maximum is None:
        return ""
    range_text = f"{minimum or ''} - {maximum or ''}".strip(" -")
    return " ".join(value for value in [currency, range_text, interval] if value)
