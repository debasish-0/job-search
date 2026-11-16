# Validation Report

Validation date: 2026-11-16

## Automated checks completed

- Python syntax compilation: passed
- Package build and installation from `pyproject.toml`: passed
- Unit and integration tests: 11 passed
- Greenhouse normalization test: passed
- Lever normalization test: passed
- Ashby normalization test: passed
- Relevant-versus-unrelated scoring test: passed
- Excluded-keyword hard-block test: passed
- SQLite duplicate merge, score persistence, and status history test: passed
- Complete offline workflow test: passed
- Repeat-run digest suppression and forced-rescore behavior: passed
- Digest creation test: passed
- Approval-gated application-package creation test: passed
- FastAPI smoke checks for `/health`, `/metrics`, `/jobs`, and `/runs`: passed
- Docker Compose YAML parse check: passed

## Demonstration result

Using the included example profile and three sample jobs on a clean database:

- Jobs discovered: 3
- New jobs stored: 3
- Strong matches on first run: 1
- Strong matches on unchanged repeat run: 0
- Strong matches on forced rescore: 1
- Full-stack role score: 97.2
- Unrelated principal Java role score: 27.8
- Unpaid internship score: 0.0 because of the configured hard block

The approved sample role generated:

- `application_checklist.md`
- `cover_letter.md`
- `job_snapshot.md`
- `match_analysis.json`
- `resume_tailoring_plan.md`
- a copied source resume
- `targeted_resume_draft.docx`

## Not executed in this build environment

- Live calls to third-party ATS endpoints were not made from the build container. Collector tests use response shapes from the official Greenhouse, Lever, and Ashby documentation.
- Ollama model inference was not executed because the models were not installed in the build container. The offline fallback path was executed end to end.
- The Streamlit server was not launched because Streamlit was not installed in the build container. Its module passed Python syntax compilation.
- A Docker image was not built because Docker was not available in the build container.
