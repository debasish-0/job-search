from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import CandidateProfile


@dataclass(slots=True)
class AppSettings:
    database_path: Path
    output_dir: Path
    digest_dir: Path
    profile_path: Path
    user_agent: str = "OpenSourceAIJobSearch/0.1"
    request_timeout_seconds: int = 30
    request_delay_seconds: float = 0.25


@dataclass(slots=True)
class WorkflowSettings:
    minimum_match_score: float = 68.0
    llm_analysis_minimum_score: float = 76.0
    max_llm_analyses_per_run: int = 10
    schedule_hours: float = 12.0
    inactive_after_days: int = 30
    write_digest: bool = True
    send_email_digest: bool = False


@dataclass(slots=True)
class ScoringSettings:
    semantic_weight: float = 0.45
    skills_weight: float = 0.25
    title_weight: float = 0.15
    location_weight: float = 0.10
    experience_weight: float = 0.05

    def normalized(self) -> "ScoringSettings":
        total = (
            self.semantic_weight
            + self.skills_weight
            + self.title_weight
            + self.location_weight
            + self.experience_weight
        )
        if total <= 0:
            raise ValueError("Scoring weights must add to a positive number")
        self.semantic_weight /= total
        self.skills_weight /= total
        self.title_weight /= total
        self.location_weight /= total
        self.experience_weight /= total
        return self


@dataclass(slots=True)
class AISettings:
    enabled: bool = True
    base_url: str = "http://localhost:11434"
    chat_model: str = "qwen3:4b-instruct"
    embedding_model: str = "nomic-embed-text"
    request_timeout_seconds: int = 180
    max_resume_characters: int = 16000
    max_job_characters: int = 14000


@dataclass(slots=True)
class SourceTarget:
    kind: str
    identifier: str
    company: str = ""
    enabled: bool = True
    region: str = "global"
    include_compensation: bool = True


@dataclass(slots=True)
class AppConfig:
    config_path: Path
    root_dir: Path
    app: AppSettings
    candidate: CandidateProfile
    workflow: WorkflowSettings
    scoring: ScoringSettings
    ai: AISettings
    sources: list[SourceTarget] = field(default_factory=list)


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


def _root_for_config(config_path: Path) -> Path:
    parent = config_path.resolve().parent
    if parent.name.lower() == "config":
        return parent.parent
    return parent


def _load_profile_overlay(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(
        path or os.getenv("JOBSEARCH_CONFIG", "config/settings.toml")
    ).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. Copy config/settings.toml first."
        )

    root = _root_for_config(config_path)
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    app_raw = raw.get("app", {})
    app = AppSettings(
        database_path=_resolve_path(root, app_raw.get("database_path", "data/jobsearch.db")),
        output_dir=_resolve_path(root, app_raw.get("output_dir", "data/applications")),
        digest_dir=_resolve_path(root, app_raw.get("digest_dir", "data/digests")),
        profile_path=_resolve_path(root, app_raw.get("profile_path", "data/profile.json")),
        user_agent=str(app_raw.get("user_agent", "OpenSourceAIJobSearch/0.1")),
        request_timeout_seconds=int(app_raw.get("request_timeout_seconds", 30)),
        request_delay_seconds=float(app_raw.get("request_delay_seconds", 0.25)),
    )

    candidate_raw = dict(raw.get("candidate", {}))
    overlay = _load_profile_overlay(app.profile_path)
    for key, value in overlay.items():
        if value in (None, "", []):
            continue
        if key == "years_experience":
            try:
                if float(value) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
        candidate_raw[key] = value

    resume_path_value = str(candidate_raw.get("resume_path", ""))
    resume_path = _resolve_path(root, resume_path_value) if resume_path_value else Path()
    candidate = CandidateProfile(
        name=str(candidate_raw.get("name", "")),
        email=str(candidate_raw.get("email", "")),
        phone=str(candidate_raw.get("phone", "")),
        location=str(candidate_raw.get("location", "")),
        current_title=str(candidate_raw.get("current_title", "")),
        years_experience=float(candidate_raw.get("years_experience", 0) or 0),
        target_roles=_list(candidate_raw.get("target_roles")),
        preferred_locations=_list(candidate_raw.get("preferred_locations")),
        workplace_preferences=[
            item.lower() for item in _list(candidate_raw.get("workplace_preferences"))
        ],
        skills=_list(candidate_raw.get("skills")),
        include_keywords=_list(candidate_raw.get("include_keywords")),
        exclude_keywords=_list(candidate_raw.get("exclude_keywords")),
        resume_path=str(resume_path) if resume_path_value else "",
        summary=str(candidate_raw.get("summary", "")),
        experience_highlights=_list(candidate_raw.get("experience_highlights")),
    )

    workflow_raw = raw.get("workflow", {})
    workflow = WorkflowSettings(
        minimum_match_score=float(workflow_raw.get("minimum_match_score", 68)),
        llm_analysis_minimum_score=float(
            workflow_raw.get("llm_analysis_minimum_score", 76)
        ),
        max_llm_analyses_per_run=int(
            workflow_raw.get("max_llm_analyses_per_run", 10)
        ),
        schedule_hours=float(workflow_raw.get("schedule_hours", 12)),
        inactive_after_days=int(workflow_raw.get("inactive_after_days", 30)),
        write_digest=bool(workflow_raw.get("write_digest", True)),
        send_email_digest=bool(workflow_raw.get("send_email_digest", False)),
    )

    scoring_raw = raw.get("scoring", {})
    scoring = ScoringSettings(
        semantic_weight=float(scoring_raw.get("semantic_weight", 0.45)),
        skills_weight=float(scoring_raw.get("skills_weight", 0.25)),
        title_weight=float(scoring_raw.get("title_weight", 0.15)),
        location_weight=float(scoring_raw.get("location_weight", 0.10)),
        experience_weight=float(scoring_raw.get("experience_weight", 0.05)),
    ).normalized()

    ai_raw = raw.get("ai", {})
    ai = AISettings(
        enabled=bool(ai_raw.get("enabled", True)),
        base_url=os.getenv(
            "OLLAMA_BASE_URL", str(ai_raw.get("base_url", "http://localhost:11434"))
        ).rstrip("/"),
        chat_model=os.getenv(
            "OLLAMA_CHAT_MODEL", str(ai_raw.get("chat_model", "qwen3:4b-instruct"))
        ),
        embedding_model=os.getenv(
            "OLLAMA_EMBEDDING_MODEL",
            str(ai_raw.get("embedding_model", "nomic-embed-text")),
        ),
        request_timeout_seconds=int(ai_raw.get("request_timeout_seconds", 180)),
        max_resume_characters=int(ai_raw.get("max_resume_characters", 16000)),
        max_job_characters=int(ai_raw.get("max_job_characters", 14000)),
    )

    source_raw = raw.get("sources", {})
    sources: list[SourceTarget] = []
    for item in source_raw.get("greenhouse", []):
        sources.append(
            SourceTarget(
                kind="greenhouse",
                identifier=str(item.get("board", "")).strip(),
                company=str(item.get("company", "")).strip(),
                enabled=bool(item.get("enabled", True)),
            )
        )
    for item in source_raw.get("lever", []):
        sources.append(
            SourceTarget(
                kind="lever",
                identifier=str(item.get("site", "")).strip(),
                company=str(item.get("company", "")).strip(),
                enabled=bool(item.get("enabled", True)),
                region=str(item.get("region", "global")).lower(),
            )
        )
    for item in source_raw.get("ashby", []):
        sources.append(
            SourceTarget(
                kind="ashby",
                identifier=str(item.get("board", "")).strip(),
                company=str(item.get("company", "")).strip(),
                enabled=bool(item.get("enabled", True)),
                include_compensation=bool(item.get("include_compensation", True)),
            )
        )
    for item in source_raw.get("local_json", []):
        raw_path = str(item.get("path", "")).strip()
        sources.append(
            SourceTarget(
                kind="local_json",
                identifier=str(_resolve_path(root, raw_path)) if raw_path else "",
                company=str(item.get("company", "")).strip(),
                enabled=bool(item.get("enabled", True)),
            )
        )

    app.database_path.parent.mkdir(parents=True, exist_ok=True)
    app.output_dir.mkdir(parents=True, exist_ok=True)
    app.digest_dir.mkdir(parents=True, exist_ok=True)
    app.profile_path.parent.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        config_path=config_path,
        root_dir=root,
        app=app,
        candidate=candidate,
        workflow=workflow,
        scoring=scoring,
        ai=ai,
        sources=[source for source in sources if source.enabled and source.identifier],
    )
