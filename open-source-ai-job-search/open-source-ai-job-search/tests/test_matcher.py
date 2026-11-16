from __future__ import annotations

import unittest

from jobsearch.ai.matcher import JobMatcher
from jobsearch.config import ScoringSettings
from jobsearch.models import CandidateProfile, Job


class MatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = CandidateProfile(
            current_title="Full Stack Developer",
            years_experience=5,
            target_roles=["Senior Full Stack Engineer", "Software Engineer"],
            preferred_locations=["Pune", "India", "Remote"],
            workplace_preferences=["remote", "hybrid"],
            skills=[
                "Python",
                "FastAPI",
                "React",
                "TypeScript",
                "PostgreSQL",
                "Azure",
                "Docker",
                "Pytest",
            ],
            exclude_keywords=["unpaid"],
            resume_text="Built React applications and FastAPI services using PostgreSQL and Azure.",
        )
        self.matcher = JobMatcher(ScoringSettings().normalized(), ollama=None)

    def test_relevant_job_scores_higher(self) -> None:
        relevant = Job(
            source="test",
            source_job_id="1",
            company="Acme",
            title="Senior Full Stack Engineer",
            location="Remote - India",
            workplace_type="remote",
            description=(
                "Build React and TypeScript applications with Python, FastAPI, PostgreSQL, "
                "Azure, Docker and Pytest. Requires 4-7 years of experience."
            ),
        ).finalize()
        unrelated = Job(
            source="test",
            source_job_id="2",
            company="Acme",
            title="Principal Java Platform Manager",
            location="London",
            workplace_type="on-site",
            description="Lead Java and Kafka teams. Requires 12+ years of experience.",
        ).finalize()
        relevant_score = self.matcher.score_job(self.profile, relevant).score
        unrelated_score = self.matcher.score_job(self.profile, unrelated).score
        self.assertGreater(relevant_score, 70)
        self.assertGreater(relevant_score, unrelated_score + 20)

    def test_excluded_keyword_blocks_job(self) -> None:
        job = Job(
            source="test",
            source_job_id="3",
            company="Acme",
            title="React Intern",
            description="This is an unpaid internship.",
        ).finalize()
        result = self.matcher.score_job(self.profile, job)
        self.assertTrue(result.blocked)
        self.assertEqual(result.score, 0)


if __name__ == "__main__":
    unittest.main()
