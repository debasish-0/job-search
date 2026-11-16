from __future__ import annotations

from typing import Any

from ..http import HttpJsonClient
from ..models import Job
from ..text import stable_hash, strip_html


class AshbyCollector:
    name = "ashby"

    def __init__(
        self,
        board: str,
        company: str,
        client: HttpJsonClient,
        include_compensation: bool = True,
    ) -> None:
        self.board = board
        self.company = company or board
        self.client = client
        self.include_compensation = include_compensation

    def collect(self) -> list[Job]:
        payload = self.client.get_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{self.board}",
            {"includeCompensation": str(self.include_compensation).lower()},
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected Ashby response for {self.board}")
        jobs: list[Job] = []
        for item in payload.get("jobs", []):
            if not isinstance(item, dict) or item.get("isListed") is False:
                continue
            job_url = str(item.get("jobUrl") or "")
            source_id = str(item.get("id") or item.get("jobPostingId") or "")
            if not source_id:
                source_id = stable_hash(job_url, str(item.get("title") or ""))[:24]
            jobs.append(
                Job(
                    source=self.name,
                    source_job_id=source_id,
                    company=self.company,
                    title=str(item.get("title") or "Untitled role"),
                    location=_location(item),
                    workplace_type=str(
                        item.get("workplaceType")
                        or ("Remote" if item.get("isRemote") else "")
                    ),
                    description=strip_html(
                        str(item.get("descriptionPlain") or item.get("descriptionHtml") or "")
                    ),
                    job_url=job_url,
                    apply_url=str(item.get("applyUrl") or job_url),
                    department=str(item.get("department") or item.get("team") or ""),
                    employment_type=str(item.get("employmentType") or ""),
                    salary_text=_compensation(item),
                    posted_at=str(item.get("publishedAt") or ""),
                ).finalize()
            )
        return jobs


def _location(item: dict[str, Any]) -> str:
    primary = str(item.get("location") or "").strip()
    secondary = item.get("secondaryLocations") or []
    locations = [primary] if primary else []
    for value in secondary:
        if isinstance(value, dict) and value.get("location"):
            locations.append(str(value["location"]))
    return ", ".join(dict.fromkeys(locations))


def _compensation(item: dict[str, Any]) -> str:
    compensation = item.get("compensation")
    if not isinstance(compensation, dict):
        return ""
    return str(
        compensation.get("compensationTierSummary")
        or compensation.get("scrapeableCompensationSalarySummary")
        or ""
    )
