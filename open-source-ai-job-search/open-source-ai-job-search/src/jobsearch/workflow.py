from __future__ import annotations

from collections import OrderedDict
from typing import Any

from .ai import JobAnalyzer, JobMatcher, OllamaClient, job_from_record
from .collectors import Collector, build_collectors
from .config import AppConfig
from .db import Repository
from .digest import DigestService, EmailNotifier
from .models import Job, WorkflowStats
from .parsers import ResumeParseError, read_resume


class JobSearchWorkflow:
    def __init__(
        self,
        config: AppConfig,
        repository: Repository | None = None,
        collectors: list[Collector] | None = None,
    ) -> None:
        self.config = config
        self.repository = repository or Repository(config.app.database_path)
        self.collectors = collectors if collectors is not None else build_collectors(config)
        self.ollama = OllamaClient(config.ai, config.app.user_agent)
        self.matcher = JobMatcher(config.scoring, self.ollama)
        self.analyzer = JobAnalyzer(self.ollama, config.ai)

    def run(self, rescore: bool = False, use_llm: bool = True) -> WorkflowStats:
        run_id = self.repository.start_run()
        stats = WorkflowStats(run_id=run_id)
        try:
            self._load_resume(stats)
            job_ids: list[int] = []
            fresh_job_ids: set[int] = set()
            unique_keys: set[str] = set()
            for collector in self.collectors:
                try:
                    jobs = collector.collect()
                    stats.discovered += len(jobs)
                    for job in jobs:
                        job.finalize()
                        unique_keys.add(job.canonical_key)
                        job_id, inserted, changed = self.repository.upsert_job(job, run_id)
                        job_ids.append(job_id)
                        stats.inserted += int(inserted)
                        stats.updated += int(changed and not inserted)
                        if inserted or changed:
                            fresh_job_ids.add(job_id)
                except Exception as exc:
                    stats.errors.append(f"{collector.name}: {exc}")

            stats.unique = len(unique_keys)
            ordered_ids = list(OrderedDict.fromkeys(job_ids))
            if rescore:
                ordered_ids = [
                    int(job["id"])
                    for job in self.repository.list_jobs(
                        minimum_score=0, active_only=True, limit=100000
                    )
                ]
            records = self.repository.jobs_for_scoring(ordered_ids, rescore=rescore)
            job_pairs = [
                (int(record["id"]), job_from_record(record)) for record in records
            ]
            matcher = self.matcher if use_llm else JobMatcher(self.config.scoring, None)
            scored = matcher.score_many(self.config.candidate, job_pairs)
            result_by_id: dict[int, Any] = {}
            for job_id, result in scored:
                self.repository.save_score(job_id, result)
                result_by_id[job_id] = result
                stats.scored += 1

            if use_llm and self.ollama.is_available():
                candidates = sorted(
                    (
                        (job_id, result)
                        for job_id, result in result_by_id.items()
                        if result.score >= self.config.workflow.llm_analysis_minimum_score
                    ),
                    key=lambda value: value[1].score,
                    reverse=True,
                )[: self.config.workflow.max_llm_analyses_per_run]
                record_map = {int(record["id"]): record for record in records}
                for job_id, result in candidates:
                    try:
                        analysis = self.analyzer.analyze(
                            self.config.candidate,
                            job_from_record(record_map[job_id]),
                            result,
                        )
                        if analysis:
                            self.repository.save_analysis(job_id, analysis)
                            stats.llm_analyses += 1
                    except RuntimeError as exc:
                        stats.errors.append(f"ollama analysis for job {job_id}: {exc}")
                        break

            self.repository.deactivate_stale(self.config.workflow.inactive_after_days)
            digest_job_ids = ordered_ids if rescore else sorted(fresh_job_ids)
            strong_jobs = self.repository.jobs_by_ids(
                digest_job_ids, self.config.workflow.minimum_match_score
            )
            stats.strong_matches = len(strong_jobs)
            if self.config.workflow.write_digest:
                digest = DigestService(self.config.app.digest_dir).write(
                    run_id, strong_jobs, stats.errors
                )
                stats.digest_path = str(digest)
                if self.config.workflow.send_email_digest:
                    try:
                        EmailNotifier().send_digest(
                            digest,
                            f"AI Job Search Digest - {len(strong_jobs)} strong matches",
                        )
                    except RuntimeError as exc:
                        stats.errors.append(f"email digest: {exc}")

            status = "partial" if stats.errors else "completed"
            self.repository.finish_run(run_id, status, stats.to_dict())
            return stats
        except Exception as exc:
            stats.errors.append(str(exc))
            self.repository.finish_run(
                run_id,
                "failed",
                stats.to_dict(),
                error_text=str(exc),
            )
            raise

    def _load_resume(self, stats: WorkflowStats) -> None:
        path = self.config.candidate.resume_path
        if not path:
            return
        try:
            self.config.candidate.resume_text = read_resume(path)
        except ResumeParseError as exc:
            stats.errors.append(f"resume: {exc}")
