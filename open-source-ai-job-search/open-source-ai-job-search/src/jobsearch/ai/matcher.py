from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from ..config import ScoringSettings
from ..models import CandidateProfile, Job, MatchResult
from ..text import (
    contains_phrase,
    cosine_similarity,
    lexical_cosine,
    normalize_key,
    tokenize,
)
from .ollama import OllamaClient


COMMON_SKILLS = [
    "Python",
    "Java",
    "C#",
    "C++",
    "Go",
    "Rust",
    "JavaScript",
    "TypeScript",
    "React",
    "Next.js",
    "Angular",
    "Vue",
    "Node.js",
    "FastAPI",
    "Django",
    "Flask",
    "Spring Boot",
    ".NET",
    "PostgreSQL",
    "MySQL",
    "SQL Server",
    "MongoDB",
    "Redis",
    "Kafka",
    "REST API",
    "GraphQL",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "Terraform",
    "GitHub Actions",
    "CI/CD",
    "Pytest",
    "Jest",
    "Cypress",
    "Playwright",
    "Machine Learning",
    "LLM",
    "LangChain",
    "LangGraph",
    "Microservices",
    "System Design",
]


class JobMatcher:
    def __init__(
        self,
        scoring: ScoringSettings,
        ollama: OllamaClient | None = None,
    ) -> None:
        self.scoring = scoring
        self.ollama = ollama

    def score_many(
        self,
        profile: CandidateProfile,
        jobs: list[tuple[int, Job]],
    ) -> list[tuple[int, MatchResult]]:
        semantic_scores = self._semantic_scores(profile, [job for _, job in jobs])
        results: list[tuple[int, MatchResult]] = []
        for index, (job_id, job) in enumerate(jobs):
            results.append(
                (
                    job_id,
                    self.score_job(
                        profile,
                        job,
                        semantic_score=semantic_scores[index],
                    ),
                )
            )
        return results

    def score_job(
        self,
        profile: CandidateProfile,
        job: Job,
        semantic_score: float | None = None,
    ) -> MatchResult:
        combined = job.matching_text()
        blocked_phrase = next(
            (
                phrase
                for phrase in profile.exclude_keywords
                if contains_phrase(combined, phrase)
            ),
            "",
        )
        if blocked_phrase:
            return MatchResult(
                score=0.0,
                semantic_score=0.0,
                skills_score=0.0,
                title_score=0.0,
                location_score=0.0,
                experience_score=0.0,
                reasons=[f"Blocked by excluded keyword: {blocked_phrase}"],
                blocked=True,
                blocked_reason=blocked_phrase,
            )

        semantic = (
            semantic_score
            if semantic_score is not None
            else self._fallback_semantic(profile.matching_text(), combined)
        )
        skills_score, matched_skills, missing_skills = self._skills(profile, job)
        title_score = self._title(profile, job)
        location_score = self._location(profile, job)
        experience_score = self._experience(profile.years_experience, combined)

        include_bonus = 0.0
        if profile.include_keywords:
            matches = sum(
                1 for phrase in profile.include_keywords if contains_phrase(combined, phrase)
            )
            include_bonus = min(0.05, 0.01 * matches)

        weighted = (
            semantic * self.scoring.semantic_weight
            + skills_score * self.scoring.skills_weight
            + title_score * self.scoring.title_weight
            + location_score * self.scoring.location_weight
            + experience_score * self.scoring.experience_weight
            + include_bonus
        )
        score = round(max(0.0, min(1.0, weighted)) * 100, 1)
        reasons = self._reasons(
            semantic,
            skills_score,
            title_score,
            location_score,
            experience_score,
            matched_skills,
            missing_skills,
        )
        return MatchResult(
            score=score,
            semantic_score=round(semantic * 100, 1),
            skills_score=round(skills_score * 100, 1),
            title_score=round(title_score * 100, 1),
            location_score=round(location_score * 100, 1),
            experience_score=round(experience_score * 100, 1),
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            reasons=reasons,
        )

    def _semantic_scores(
        self, profile: CandidateProfile, jobs: list[Job]
    ) -> list[float]:
        profile_text = profile.matching_text()
        if self.ollama and self.ollama.is_available():
            try:
                texts = [profile_text] + [job.matching_text() for job in jobs]
                embeddings = self.ollama.embed_many(texts)
                profile_embedding = embeddings[0]
                return [
                    max(0.0, cosine_similarity(profile_embedding, embedding))
                    for embedding in embeddings[1:]
                ]
            except RuntimeError:
                pass
        return [
            self._fallback_semantic(profile_text, job.matching_text()) for job in jobs
        ]

    @staticmethod
    def _fallback_semantic(profile_text: str, job_text: str) -> float:
        raw = lexical_cosine(profile_text, job_text)
        return max(0.0, min(1.0, 0.15 + (2.0 * raw)))

    @staticmethod
    def _skills(
        profile: CandidateProfile, job: Job
    ) -> tuple[float, list[str], list[str]]:
        description = job.matching_text()
        universe = list(dict.fromkeys([*COMMON_SKILLS, *profile.skills]))
        job_skills = [skill for skill in universe if contains_phrase(description, skill)]
        candidate_skills = {normalize_key(skill) for skill in profile.skills}
        matched = [
            skill for skill in job_skills if normalize_key(skill) in candidate_skills
        ]
        missing = [
            skill for skill in job_skills if normalize_key(skill) not in candidate_skills
        ]
        if job_skills:
            score = len(matched) / len(job_skills)
        else:
            profile_mentions = sum(
                1 for skill in profile.skills if contains_phrase(description, skill)
            )
            score = min(1.0, profile_mentions / max(3, len(profile.skills) * 0.35))
        return score, sorted(set(matched)), sorted(set(missing))

    @staticmethod
    def _title(profile: CandidateProfile, job: Job) -> float:
        targets = profile.target_roles or [profile.current_title]
        targets = [target for target in targets if target]
        if not targets:
            return 0.5
        job_key = normalize_key(job.title)
        job_tokens = set(tokenize(job.title))
        scores: list[float] = []
        for target in targets:
            target_key = normalize_key(target)
            ratio = SequenceMatcher(None, target_key, job_key).ratio()
            target_tokens = set(tokenize(target))
            union = job_tokens | target_tokens
            overlap = len(job_tokens & target_tokens) / len(union) if union else 0.0
            scores.append((ratio * 0.65) + (overlap * 0.35))
        return max(scores, default=0.0)

    @staticmethod
    def _location(profile: CandidateProfile, job: Job) -> float:
        workplace = normalize_key(job.workplace_type)
        location = normalize_key(job.location)
        preferences = {normalize_key(value) for value in profile.workplace_preferences}
        if "remote" in workplace or "remote" in location:
            return 1.0 if not preferences or "remote" in preferences else 0.65
        if "hybrid" in workplace or "hybrid" in location:
            return 1.0 if not preferences or "hybrid" in preferences else 0.7
        if any(
            normalize_key(preferred) in location
            for preferred in profile.preferred_locations
            if normalize_key(preferred)
        ):
            return 1.0
        if not location:
            return 0.55
        return 0.25

    @staticmethod
    def _experience(candidate_years: float, text: str) -> float:
        ranges = re.findall(
            r"(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:\+\s*)?years?",
            text,
            flags=re.I,
        )
        if ranges:
            lower, upper = max((int(a), int(b)) for a, b in ranges)
            if lower <= candidate_years <= upper:
                return 1.0
            if candidate_years < lower:
                return max(0.0, 1.0 - ((lower - candidate_years) * 0.25))
            return 0.8
        minimums = [
            int(value)
            for value in re.findall(
                r"(?:minimum\s+of\s+|at\s+least\s+)?(\d{1,2})\+?\s*years?",
                text,
                flags=re.I,
            )
        ]
        if not minimums:
            return 0.75
        minimum = max(minimums)
        if candidate_years >= minimum:
            return 1.0
        return max(0.0, 1.0 - ((minimum - candidate_years) * 0.25))

    @staticmethod
    def _reasons(
        semantic: float,
        skills: float,
        title: float,
        location: float,
        experience: float,
        matched_skills: list[str],
        missing_skills: list[str],
    ) -> list[str]:
        reasons = [
            f"Semantic relevance: {semantic * 100:.0f}%",
            f"Role-title fit: {title * 100:.0f}%",
            f"Location fit: {location * 100:.0f}%",
            f"Experience fit: {experience * 100:.0f}%",
        ]
        if matched_skills:
            reasons.append("Matched skills: " + ", ".join(matched_skills[:10]))
        if missing_skills:
            reasons.append("Potential skill gaps: " + ", ".join(missing_skills[:10]))
        if not matched_skills and skills < 0.5:
            reasons.append("Few explicit candidate skills were found in the description")
        return reasons


def job_from_record(record: dict[str, Any]) -> Job:
    return Job(
        source=str(record.get("source") or ""),
        source_job_id=str(record.get("source_job_id") or ""),
        company=str(record.get("company") or ""),
        title=str(record.get("title") or ""),
        location=str(record.get("location") or ""),
        workplace_type=str(record.get("workplace_type") or ""),
        description=str(record.get("description") or ""),
        job_url=str(record.get("job_url") or ""),
        apply_url=str(record.get("apply_url") or ""),
        department=str(record.get("department") or ""),
        employment_type=str(record.get("employment_type") or ""),
        salary_text=str(record.get("salary_text") or ""),
        posted_at=str(record.get("posted_at") or ""),
    ).finalize()
