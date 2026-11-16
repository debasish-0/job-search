from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jobsearch.db import Repository
from jobsearch.models import Job, MatchResult


class RepositoryTests(unittest.TestCase):
    def test_upsert_deduplicate_score_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "jobs.db")
            run_id = repository.start_run()
            first = Job(
                source="greenhouse",
                source_job_id="1",
                company="Acme",
                title="Software Engineer",
                location="Pune",
                description="Python and React",
            ).finalize()
            job_id, inserted, changed = repository.upsert_job(first, run_id)
            self.assertTrue(inserted)
            self.assertTrue(changed)

            duplicate = Job(
                source="lever",
                source_job_id="another",
                company="Acme",
                title="Software Engineer",
                location="Pune",
                description="Python and React",
            ).finalize()
            duplicate_id, inserted, _ = repository.upsert_job(duplicate, run_id)
            self.assertEqual(duplicate_id, job_id)
            self.assertFalse(inserted)

            result = MatchResult(
                score=88,
                semantic_score=90,
                skills_score=85,
                title_score=90,
                location_score=100,
                experience_score=80,
            )
            repository.save_score(job_id, result)
            repository.set_status(job_id, "approved", "Looks relevant")
            stored = repository.get_job(job_id)
            self.assertEqual(stored["status"], "approved")
            self.assertEqual(stored["score"], 88)
            self.assertEqual(len(repository.get_events(job_id)), 1)
            self.assertIn("lever", stored["alternate_sources"])


if __name__ == "__main__":
    unittest.main()
