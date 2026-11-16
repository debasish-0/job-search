from __future__ import annotations

import unittest
from typing import Any

from jobsearch.collectors.ashby import AshbyCollector
from jobsearch.collectors.greenhouse import GreenhouseCollector
from jobsearch.collectors.lever import LeverCollector


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses

    def get_json(self, url: str, params: dict[str, Any] | None = None):
        for key, value in self.responses.items():
            if key in url:
                return value
        raise AssertionError(f"Unexpected URL: {url}")


class CollectorTests(unittest.TestCase):
    def test_greenhouse_normalization(self) -> None:
        client = FakeClient(
            {
                "/jobs": {
                    "jobs": [
                        {
                            "id": 123,
                            "title": "Full Stack Engineer",
                            "location": {"name": "Remote"},
                            "absolute_url": "https://example/jobs/123",
                            "content": "<p>Python and React</p>",
                            "updated_at": "2026-01-01T00:00:00Z",
                            "departments": [{"name": "Engineering"}],
                        }
                    ]
                },
                "/v1/boards/acme": {"name": "Acme"},
            }
        )
        jobs = GreenhouseCollector("acme", "", client).collect()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Acme")
        self.assertEqual(jobs[0].description, "Python and React")
        self.assertEqual(jobs[0].department, "Engineering")

    def test_lever_normalization(self) -> None:
        client = FakeClient(
            {
                "/v0/postings/acme": [
                    {
                        "id": "abc",
                        "text": "Backend Engineer",
                        "categories": {
                            "location": "Pune",
                            "commitment": "Full-time",
                            "department": "Platform",
                        },
                        "descriptionPlain": "Build Python APIs",
                        "hostedUrl": "https://jobs.example/abc",
                        "applyUrl": "https://jobs.example/abc/apply",
                        "workplaceType": "hybrid",
                    }
                ]
            }
        )
        jobs = LeverCollector("acme", "Acme", client).collect()
        self.assertEqual(jobs[0].employment_type, "Full-time")
        self.assertEqual(jobs[0].workplace_type, "hybrid")
        self.assertEqual(jobs[0].apply_url, "https://jobs.example/abc/apply")

    def test_ashby_normalization(self) -> None:
        client = FakeClient(
            {
                "/posting-api/job-board/Acme": {
                    "jobs": [
                        {
                            "title": "Software Engineer",
                            "location": "India",
                            "isListed": True,
                            "isRemote": True,
                            "workplaceType": "Remote",
                            "descriptionHtml": "<p>React and TypeScript</p>",
                            "jobUrl": "https://jobs.example/software",
                            "applyUrl": "https://jobs.example/software/apply",
                        }
                    ]
                }
            }
        )
        jobs = AshbyCollector("Acme", "Acme", client).collect()
        self.assertEqual(jobs[0].workplace_type, "Remote")
        self.assertEqual(jobs[0].description, "React and TypeScript")
        self.assertTrue(jobs[0].source_job_id)


if __name__ == "__main__":
    unittest.main()
