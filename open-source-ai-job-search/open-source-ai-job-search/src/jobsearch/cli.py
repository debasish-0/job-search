from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from .ai import OllamaClient, ProfileExtractor
from .config import AppConfig, load_config
from .db import Repository, VALID_STATUSES
from .drafts import ApplicationPackageBuilder
from .env import load_env_file
from .workflow import JobSearchWorkflow


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobsearch",
        description="Local-first open-source AI job-search workflow",
    )
    parser.add_argument(
        "--config",
        default=os.getenv("JOBSEARCH_CONFIG", "config/settings.toml"),
        help="Path to TOML configuration",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create or update the local SQLite database")

    run = subparsers.add_parser("run", help="Collect, score, store, and summarize jobs")
    run.add_argument("--rescore", action="store_true", help="Rescore existing jobs")
    run.add_argument("--no-llm", action="store_true", help="Disable Ollama analysis")

    listing = subparsers.add_parser("list", help="List tracked jobs")
    listing.add_argument("--min-score", type=float, default=0)
    listing.add_argument("--status", choices=sorted(VALID_STATUSES))
    listing.add_argument("--limit", type=int, default=100)

    show = subparsers.add_parser("show", help="Show one job as JSON")
    show.add_argument("job_id", type=int)

    open_job = subparsers.add_parser(
        "open", help="Open the employer-hosted application page"
    )
    open_job.add_argument("job_id", type=int)

    status = subparsers.add_parser("status", help="Update a job status")
    status.add_argument("job_id", type=int)
    status.add_argument("status", choices=sorted(VALID_STATUSES))
    status.add_argument("--notes", default="")

    approve = subparsers.add_parser("approve", help="Approve a job for drafting")
    approve.add_argument("job_id", type=int)
    approve.add_argument("--notes", default="Approved from CLI")

    draft = subparsers.add_parser("draft", help="Generate an application package")
    draft.add_argument("job_id", type=int)
    draft.add_argument("--force", action="store_true")

    extract = subparsers.add_parser(
        "extract-profile", help="Extract a structured profile from a resume"
    )
    extract.add_argument("resume")
    extract.add_argument("--output")

    serve = subparsers.add_parser("serve", help="Run the FastAPI service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    dashboard = subparsers.add_parser("dashboard", help="Run the Streamlit dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8501)

    scheduler = subparsers.add_parser(
        "scheduler", help="Run searches repeatedly in the foreground"
    )
    scheduler.add_argument("--hours", type=float)
    scheduler.add_argument("--no-llm", action="store_true")

    export = subparsers.add_parser("export", help="Export tracked jobs")
    export.add_argument("output")
    export.add_argument("--min-score", type=float, default=0)
    export.add_argument("--status", choices=sorted(VALID_STATUSES))

    subparsers.add_parser("metrics", help="Show tracker metrics")
    subparsers.add_parser("runs", help="Show recent workflow runs")
    subparsers.add_parser("sources", help="Show configured job sources")
    return parser


def _load(path: str) -> tuple[AppConfig, Repository]:
    config = load_config(path)
    return config, Repository(config.app.database_path)


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No jobs found.")
        return
    headers = ["ID", "Score", "Status", "Title", "Company", "Location"]
    rendered = []
    for row in rows:
        rendered.append(
            [
                str(row.get("id", "")),
                f"{float(row.get('score') or 0):.1f}",
                str(row.get("status", "")),
                str(row.get("title", ""))[:45],
                str(row.get("company", ""))[:28],
                str(row.get("location", ""))[:28],
            ]
        )
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rendered))
        for index in range(len(headers))
    ]
    print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rendered:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _export(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return
    if output.suffix.lower() != ".csv":
        raise ValueError("Export path must end with .csv or .json")
    fields = [
        "id",
        "score",
        "status",
        "title",
        "company",
        "location",
        "workplace_type",
        "employment_type",
        "salary_text",
        "source",
        "job_url",
        "apply_url",
        "posted_at",
        "first_seen_at",
        "last_seen_at",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    args = _parser().parse_args(argv)
    try:
        config, repository = _load(args.config)
        if args.command == "init-db":
            print(f"Database ready: {config.app.database_path}")
            return 0
        if args.command == "run":
            stats = JobSearchWorkflow(config, repository=repository).run(
                rescore=args.rescore,
                use_llm=not args.no_llm,
            )
            print(json.dumps(stats.to_dict(), indent=2))
            return 0
        if args.command == "list":
            _print_table(
                repository.list_jobs(
                    minimum_score=args.min_score,
                    status=args.status,
                    active_only=False,
                    limit=args.limit,
                )
            )
            return 0
        if args.command == "show":
            job = repository.get_job(args.job_id)
            if job is None:
                raise KeyError(f"Job {args.job_id} not found")
            job["events"] = repository.get_events(args.job_id)
            job["drafts"] = repository.get_drafts(args.job_id)
            print(json.dumps(job, indent=2))
            return 0
        if args.command == "open":
            job = repository.get_job(args.job_id)
            if job is None:
                raise KeyError(f"Job {args.job_id} not found")
            url = str(job.get("apply_url") or job.get("job_url") or "")
            if not url:
                raise ValueError(f"Job {args.job_id} has no application URL")
            opened = webbrowser.open(url)
            print(f"Application URL: {url}")
            if not opened:
                print("The browser did not confirm that it opened; copy the URL manually.")
            return 0
        if args.command == "status":
            repository.set_status(args.job_id, args.status, args.notes)
            print(f"Job {args.job_id} updated to {args.status}.")
            return 0
        if args.command == "approve":
            repository.set_status(args.job_id, "approved", args.notes)
            print(f"Job {args.job_id} approved.")
            return 0
        if args.command == "draft":
            ollama = OllamaClient(config.ai, config.app.user_agent)
            output = ApplicationPackageBuilder(config, repository, ollama).build(
                args.job_id, force=args.force
            )
            print(f"Application package: {output}")
            return 0
        if args.command == "extract-profile":
            ollama = OllamaClient(config.ai, config.app.user_agent)
            extractor = ProfileExtractor(ollama, config.ai)
            profile = extractor.extract(args.resume)
            output = Path(args.output).resolve() if args.output else config.app.profile_path
            extractor.save(profile, output)
            print(json.dumps({"output": str(output), "profile": profile}, indent=2))
            return 0
        if args.command == "serve":
            try:
                import uvicorn
            except ImportError as exc:
                raise RuntimeError("Install API dependencies with: pip install -e '.[api]'") from exc
            from .api import create_app

            if args.reload:
                os.environ["JOBSEARCH_CONFIG"] = str(config.config_path)
                uvicorn.run(
                    "jobsearch.api:create_app",
                    factory=True,
                    host=args.host,
                    port=args.port,
                    reload=True,
                )
            else:
                uvicorn.run(
                    create_app(config.config_path),
                    host=args.host,
                    port=args.port,
                )
            return 0
        if args.command == "dashboard":
            dashboard_path = Path(__file__).with_name("dashboard.py")
            command = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(dashboard_path),
                f"--server.address={args.host}",
                f"--server.port={args.port}",
                "--",
                "--config",
                str(config.config_path),
            ]
            return subprocess.call(command)
        if args.command == "scheduler":
            interval = args.hours or config.workflow.schedule_hours
            if interval <= 0:
                raise ValueError("Scheduler interval must be greater than zero")
            print(f"Running immediately, then every {interval:g} hours. Press Ctrl+C to stop.")
            while True:
                try:
                    stats = JobSearchWorkflow(config, repository=repository).run(
                        rescore=False,
                        use_llm=not args.no_llm,
                    )
                    print(json.dumps(stats.to_dict(), indent=2))
                except Exception as exc:
                    print(f"Scheduled run failed: {exc}", file=sys.stderr)
                time.sleep(interval * 3600)
        if args.command == "export":
            rows = repository.list_jobs(
                minimum_score=args.min_score,
                status=args.status,
                active_only=False,
                limit=100000,
            )
            output = Path(args.output).expanduser().resolve()
            _export(rows, output)
            print(f"Exported {len(rows)} jobs to {output}")
            return 0
        if args.command == "metrics":
            print(json.dumps(repository.metrics(), indent=2))
            return 0
        if args.command == "runs":
            print(json.dumps(repository.list_runs(), indent=2))
            return 0
        if args.command == "sources":
            print(
                json.dumps(
                    [
                        {
                            "kind": source.kind,
                            "identifier": source.identifier,
                            "company": source.company,
                            "region": source.region,
                        }
                        for source in config.sources
                    ],
                    indent=2,
                )
            )
            return 0
    except KeyboardInterrupt:
        print("Stopped.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
