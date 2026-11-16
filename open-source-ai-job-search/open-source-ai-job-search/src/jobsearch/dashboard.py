from __future__ import annotations

import argparse
import os
from pathlib import Path

from jobsearch.ai import OllamaClient
from jobsearch.config import load_config
from jobsearch.db import Repository, VALID_STATUSES
from jobsearch.drafts import ApplicationPackageBuilder
from jobsearch.workflow import JobSearchWorkflow


def _config_from_args() -> str | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config")
    args, _ = parser.parse_known_args()
    return args.config or os.getenv("JOBSEARCH_CONFIG")


def main() -> None:
    try:
        import pandas as pd
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError(
            "Dashboard support requires: pip install -e '.[dashboard]'"
        ) from exc

    st.set_page_config(
        page_title="AI Job Search",
        page_icon="J",
        layout="wide",
    )
    config = load_config(_config_from_args())
    repository = Repository(config.app.database_path)
    workflow = JobSearchWorkflow(config, repository=repository)
    ollama = OllamaClient(config.ai, config.app.user_agent)
    builder = ApplicationPackageBuilder(config, repository, ollama)

    st.title("Open Source AI Job Search")
    st.caption(
        "Discover, rank, approve, draft, and track jobs locally. Applications are never auto-submitted."
    )

    with st.sidebar:
        st.header("Workflow")
        use_llm = st.checkbox("Use local Ollama AI", value=config.ai.enabled)
        rescore = st.checkbox("Rescore existing jobs", value=False)
        if st.button("Run job search", use_container_width=True, type="primary"):
            with st.spinner("Collecting and scoring jobs..."):
                stats = workflow.run(rescore=rescore, use_llm=use_llm)
            st.success(
                f"Run {stats.run_id}: {stats.strong_matches} strong matches, "
                f"{stats.inserted} new jobs."
            )
            if stats.errors:
                st.warning("\n".join(stats.errors))
        st.divider()
        st.header("Candidate")
        st.write(config.candidate.current_title)
        st.write(f"Experience: {config.candidate.years_experience:g} years")
        st.write(config.candidate.location)
        st.caption(
            f"Ollama: {'available' if ollama.is_available() else 'offline - fallback scoring active'}"
        )

    metrics = repository.metrics()
    col1, col2, col3 = st.columns(3)
    col1.metric("Active jobs", metrics["active_jobs"])
    col2.metric("Strong matches", metrics["strong_matches"])
    col3.metric("Average score", metrics["average_score"])

    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])
    with filter_col1:
        minimum_score = st.slider("Minimum score", 0, 100, 50)
    with filter_col2:
        status_options = ["All", *sorted(VALID_STATUSES)]
        selected_status = st.selectbox("Status", status_options)
    with filter_col3:
        search = st.text_input("Search title, company, or location")

    jobs = repository.list_jobs(
        minimum_score=minimum_score,
        status=None if selected_status == "All" else selected_status,
        active_only=False,
        limit=1000,
    )
    if search:
        needle = search.lower()
        jobs = [
            job
            for job in jobs
            if needle
            in " ".join(
                str(job.get(key) or "")
                for key in ("title", "company", "location", "department")
            ).lower()
        ]

    if not jobs:
        st.info("No jobs match the current filters. Run the workflow or lower the score filter.")
        return

    table = pd.DataFrame(
        [
            {
                "ID": job["id"],
                "Score": job.get("score"),
                "Status": job.get("status"),
                "Title": job.get("title"),
                "Company": job.get("company"),
                "Location": job.get("location"),
                "Source": job.get("source"),
            }
            for job in jobs
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

    labels = {
        int(job["id"]): (
            f"#{job['id']} | {float(job.get('score') or 0):.1f} | "
            f"{job.get('title')} | {job.get('company')}"
        )
        for job in jobs
    }
    selected_id = st.selectbox(
        "Review a job",
        list(labels),
        format_func=lambda value: labels[value],
    )
    job = repository.get_job(int(selected_id))
    if job is None:
        st.error("The selected job no longer exists.")
        return

    st.subheader(f"{job['title']} - {job['company']}")
    st.write(
        f"{job.get('location') or 'Location not listed'} | "
        f"{job.get('workplace_type') or 'Workplace not listed'} | "
        f"Score {float(job.get('score') or 0):.1f}"
    )
    if job.get("job_url"):
        st.link_button("Open hosted job", str(job["job_url"]))

    action_columns = st.columns(6)
    actions = [
        ("Shortlist", "shortlisted"),
        ("Approve", "approved"),
        ("Applied", "applied"),
        ("Interview", "interview"),
        ("Reject", "rejected"),
        ("Offer", "offer"),
    ]
    for column, (label, status) in zip(action_columns, actions, strict=True):
        if column.button(label, key=f"status-{status}-{selected_id}", use_container_width=True):
            repository.set_status(int(selected_id), status, "Updated from dashboard")
            st.rerun()

    if st.button("Generate approved application package"):
        try:
            with st.spinner("Generating local application documents..."):
                output = builder.build(int(selected_id))
            st.success(f"Application package created at {output}")
        except ValueError as exc:
            st.warning(str(exc))

    detail1, detail2 = st.columns(2)
    with detail1:
        st.markdown("### Match breakdown")
        st.json(job.get("score_breakdown") or {})
        st.markdown("### AI analysis")
        st.json(job.get("analysis") or {})
    with detail2:
        st.markdown("### Description")
        st.text_area(
            "Job description",
            str(job.get("description") or ""),
            height=420,
            label_visibility="collapsed",
        )

    drafts = repository.get_drafts(int(selected_id))
    if drafts:
        st.markdown("### Generated files")
        for draft in drafts:
            path = Path(str(draft["path"]))
            if path.exists() and path.is_file():
                st.download_button(
                    label=f"Download {draft['kind']}: {path.name}",
                    data=path.read_bytes(),
                    file_name=path.name,
                    key=f"download-{draft['id']}",
                )


if __name__ == "__main__":
    main()
