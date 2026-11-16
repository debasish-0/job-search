from __future__ import annotations

from pathlib import Path
from typing import Any

from .ai import OllamaClient
from .config import load_config
from .db import Repository
from .drafts import ApplicationPackageBuilder
from .workflow import JobSearchWorkflow


def create_app(config_path: str | Path | None = None):
    try:
        from fastapi import Body, FastAPI, HTTPException, Query
    except ImportError as exc:
        raise RuntimeError("API support requires: pip install -e '.[api]'") from exc

    config = load_config(config_path)
    repository = Repository(config.app.database_path)
    workflow = JobSearchWorkflow(config, repository=repository)
    ollama = OllamaClient(config.ai, config.app.user_agent)
    builder = ApplicationPackageBuilder(config, repository, ollama)

    app = FastAPI(
        title="Open Source AI Job Search",
        version="0.1.0",
        description="Local-first job discovery, matching, drafting, and tracking API",
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "database": str(config.app.database_path),
            "ollama_available": ollama.is_available(refresh=True),
            "chat_model": config.ai.chat_model,
            "embedding_model": config.ai.embedding_model,
        }

    @app.get("/profile")
    def profile() -> dict[str, Any]:
        return config.candidate.public_dict()

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        return repository.metrics()

    @app.get("/jobs")
    def jobs(
        minimum_score: float = Query(default=0, ge=0, le=100),
        status: str | None = None,
        active_only: bool = True,
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> list[dict[str, Any]]:
        return repository.list_jobs(
            minimum_score=minimum_score,
            status=status,
            active_only=active_only,
            limit=limit,
        )

    @app.get("/jobs/{job_id}")
    def job(job_id: int) -> dict[str, Any]:
        value = repository.get_job(job_id)
        if value is None:
            raise HTTPException(status_code=404, detail="Job not found")
        value["events"] = repository.get_events(job_id)
        value["drafts"] = repository.get_drafts(job_id)
        return value

    @app.patch("/jobs/{job_id}/status")
    def update_status(
        job_id: int,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        try:
            repository.set_status(
                job_id,
                str(payload.get("status") or ""),
                str(payload.get("notes") or ""),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return repository.get_job(job_id) or {}

    @app.post("/workflow/run")
    def run_workflow(
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        options = payload or {}
        stats = workflow.run(
            rescore=bool(options.get("rescore", False)),
            use_llm=bool(options.get("use_llm", True)),
        )
        return stats.to_dict()

    @app.post("/jobs/{job_id}/draft")
    def generate_draft(
        job_id: int,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        try:
            output = builder.build(job_id, force=bool((payload or {}).get("force", False)))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"job_id": job_id, "output_directory": str(output)}

    @app.get("/runs")
    def runs(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
        return repository.list_runs(limit=limit)

    return app
