from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .text import normalize_key, safe_http_url, stable_hash


@dataclass(slots=True)
class CandidateProfile:
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    current_title: str = ""
    years_experience: float = 0.0
    target_roles: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    workplace_preferences: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    resume_path: str = ""
    resume_text: str = ""
    summary: str = ""
    experience_highlights: list[str] = field(default_factory=list)

    def matching_text(self) -> str:
        sections = [
            self.current_title,
            " ".join(self.target_roles),
            " ".join(self.skills),
            self.summary,
            "\n".join(self.experience_highlights),
            self.resume_text,
        ]
        return "\n".join(section for section in sections if section).strip()

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if value.get("resume_text"):
            value["resume_text"] = f"<{len(self.resume_text)} characters loaded>"
        return value


@dataclass(slots=True)
class Job:
    source: str
    source_job_id: str
    company: str
    title: str
    location: str = ""
    workplace_type: str = ""
    description: str = ""
    job_url: str = ""
    apply_url: str = ""
    department: str = ""
    employment_type: str = ""
    salary_text: str = ""
    posted_at: str = ""
    source_key: str = ""
    canonical_key: str = ""
    content_hash: str = ""

    def finalize(self) -> "Job":
        self.job_url = safe_http_url(self.job_url)
        self.apply_url = safe_http_url(self.apply_url)
        if not self.source_job_id:
            self.source_job_id = stable_hash(
                self.company, self.title, self.location, self.job_url
            )[:24]
        self.source_key = f"{self.source}:{self.source_job_id}"
        description_signature = " ".join(
            normalize_key(self.description).split()[:120]
        )
        if not description_signature:
            description_signature = self.source_job_id or self.job_url
        self.canonical_key = stable_hash(
            self.company,
            self.title,
            self.location,
            self.department,
            description_signature,
        )
        self.content_hash = stable_hash(
            self.company,
            self.title,
            self.location,
            self.description,
            self.job_url,
            self.apply_url,
        )
        return self

    def matching_text(self) -> str:
        return "\n".join(
            value
            for value in [
                self.title,
                self.company,
                self.location,
                self.workplace_type,
                self.department,
                self.employment_type,
                self.description,
            ]
            if value
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MatchResult:
    score: float
    semantic_score: float
    skills_score: float
    title_score: float
    location_score: float
    experience_score: float
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    blocked: bool = False
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorkflowStats:
    run_id: int
    discovered: int = 0
    unique: int = 0
    inserted: int = 0
    updated: int = 0
    scored: int = 0
    strong_matches: int = 0
    llm_analyses: int = 0
    errors: list[str] = field(default_factory=list)
    digest_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
