from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jobsearch.ai import OllamaClient
from jobsearch.config import load_config
from jobsearch.db import Repository
from jobsearch.drafts import ApplicationPackageBuilder
from jobsearch.workflow import JobSearchWorkflow


class WorkflowTests(unittest.TestCase):
    def test_end_to_end_without_ollama(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "examples").mkdir()
            resume = root / "examples" / "resume.txt"
            resume.write_text(
                "Candidate\nFull Stack Developer with 5 years experience. "
                "Python FastAPI React TypeScript PostgreSQL Azure Docker.",
                encoding="utf-8",
            )
            jobs_path = root / "examples" / "jobs.json"
            jobs_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "1",
                            "company": "Acme",
                            "title": "Senior Full Stack Engineer",
                            "location": "Remote India",
                            "workplace_type": "remote",
                            "description": (
                                "React TypeScript Python FastAPI PostgreSQL Azure Docker. "
                                "Requires 4-7 years experience."
                            ),
                            "job_url": "https://example.invalid/1",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            config_path = root / "config" / "settings.toml"
            config_path.write_text(
                """
[app]
database_path = "data/jobs.db"
output_dir = "data/applications"
digest_dir = "data/digests"
profile_path = "data/profile.json"

[candidate]
name = "Candidate"
current_title = "Full Stack Developer"
years_experience = 5
resume_path = "examples/resume.txt"
target_roles = ["Senior Full Stack Engineer"]
preferred_locations = ["India", "Remote"]
workplace_preferences = ["remote"]
skills = ["Python", "FastAPI", "React", "TypeScript", "PostgreSQL", "Azure", "Docker"]

[workflow]
minimum_match_score = 65
write_digest = true
send_email_digest = false

[ai]
enabled = false

[[sources.local_json]]
path = "examples/jobs.json"
enabled = true
""".strip(),
                encoding="utf-8",
            )
            config = load_config(config_path)
            repository = Repository(config.app.database_path)
            stats = JobSearchWorkflow(config, repository=repository).run(use_llm=False)
            self.assertEqual(stats.inserted, 1)
            self.assertEqual(stats.strong_matches, 1)
            self.assertTrue(Path(stats.digest_path).exists())

            repeat = JobSearchWorkflow(config, repository=repository).run(use_llm=False)
            self.assertEqual(repeat.inserted, 0)
            self.assertEqual(repeat.updated, 0)
            self.assertEqual(repeat.strong_matches, 0)

            rescored = JobSearchWorkflow(config, repository=repository).run(
                rescore=True, use_llm=False
            )
            self.assertEqual(rescored.scored, 1)
            self.assertEqual(rescored.strong_matches, 1)

            job = repository.list_jobs()[0]
            repository.set_status(job["id"], "approved")
            builder = ApplicationPackageBuilder(
                config,
                repository,
                OllamaClient(config.ai, config.app.user_agent),
            )
            output = builder.build(job["id"])
            self.assertTrue((output / "cover_letter.md").exists())
            self.assertTrue((output / "application_checklist.md").exists())


if __name__ == "__main__":
    unittest.main()
