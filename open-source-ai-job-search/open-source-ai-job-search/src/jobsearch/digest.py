from __future__ import annotations

import html
import os
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any


class DigestService:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        run_id: int,
        jobs: list[dict[str, Any]],
        errors: list[str] | None = None,
    ) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = self.output_dir / f"job-digest-run-{run_id}-{timestamp}.html"
        rows = "\n".join(self._row(job) for job in jobs)
        error_html = ""
        if errors:
            error_html = "<h2>Source warnings</h2><ul>" + "".join(
                f"<li>{html.escape(error)}</li>" for error in errors
            ) + "</ul>"
        body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Job Search Digest</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 32px; color: #202124; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 10px; vertical-align: top; text-align: left; }}
th {{ background: #f4f6f8; }}
.score {{ font-weight: 700; }}
.small {{ color: #5f6368; font-size: 0.9rem; }}
</style>
</head>
<body>
<h1>AI Job Search Digest</h1>
<p>Workflow run {run_id}. Strong matches: {len(jobs)}.</p>
<table>
<thead><tr><th>Score</th><th>Role</th><th>Location</th><th>Why it matched</th><th>Action</th></tr></thead>
<tbody>{rows or '<tr><td colspan="5">No roles met the configured threshold.</td></tr>'}</tbody>
</table>
{error_html}
<p class="small">Review every job and generated document before applying. The workflow never submits applications.</p>
</body>
</html>
"""
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def _row(job: dict[str, Any]) -> str:
        breakdown = job.get("score_breakdown") or {}
        reasons = breakdown.get("reasons") or []
        reason_html = "<br>".join(html.escape(str(reason)) for reason in reasons[:4])
        url = html.escape(str(job.get("job_url") or job.get("apply_url") or ""), quote=True)
        apply_link = f'<a href="{url}">Review job</a>' if url else "No URL"
        return f"""
<tr>
<td class="score">{float(job.get('score') or 0):.1f}</td>
<td><strong>{html.escape(str(job.get('title') or ''))}</strong><br>{html.escape(str(job.get('company') or ''))}</td>
<td>{html.escape(str(job.get('location') or ''))}<br><span class="small">{html.escape(str(job.get('workplace_type') or ''))}</span></td>
<td>{reason_html}</td>
<td>{apply_link}</td>
</tr>
"""


class EmailNotifier:
    def configured(self) -> bool:
        return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM") and os.getenv("SMTP_TO"))

    def send_digest(self, html_path: str | Path, subject: str) -> None:
        if not self.configured():
            raise RuntimeError(
                "SMTP is not configured. Set SMTP_HOST, SMTP_FROM, and SMTP_TO."
            )
        path = Path(html_path)
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = os.environ["SMTP_FROM"]
        recipients = [
            value.strip() for value in os.environ["SMTP_TO"].split(",") if value.strip()
        ]
        message["To"] = ", ".join(recipients)
        message.set_content("Open the HTML version of this message to view the job digest.")
        message.add_alternative(path.read_text(encoding="utf-8"), subtype="html")

        host = os.environ["SMTP_HOST"]
        port = int(os.getenv("SMTP_PORT", "587"))
        username = os.getenv("SMTP_USERNAME", "")
        password = os.getenv("SMTP_PASSWORD", "")
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
        with smtplib.SMTP(host, port, timeout=30) as server:
            if use_tls:
                server.starttls()
            if username:
                server.login(username, password)
            server.send_message(message, to_addrs=recipients)
