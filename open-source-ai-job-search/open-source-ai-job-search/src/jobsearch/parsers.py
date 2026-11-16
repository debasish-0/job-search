from __future__ import annotations

import re
from pathlib import Path

from .text import normalize_whitespace


class ResumeParseError(RuntimeError):
    pass


def read_resume(path: str | Path) -> str:
    resume_path = Path(path)
    if not resume_path.exists():
        raise ResumeParseError(f"Resume file not found: {resume_path}")
    suffix = resume_path.suffix.lower()
    if suffix in {".txt", ".md", ".rst"}:
        return normalize_whitespace(resume_path.read_text(encoding="utf-8"))
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ResumeParseError(
                "PDF support requires: pip install -e '.[documents]'"
            ) from exc
        reader = PdfReader(str(resume_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return normalize_whitespace(text)
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ResumeParseError(
                "DOCX support requires: pip install -e '.[documents]'"
            ) from exc
        document = Document(str(resume_path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                paragraphs.append(" | ".join(cell.text for cell in row.cells))
        return normalize_whitespace("\n".join(paragraphs))
    raise ResumeParseError(
        f"Unsupported resume extension '{suffix}'. Use PDF, DOCX, TXT, MD, or RST."
    )


def basic_profile_hints(text: str) -> dict[str, object]:
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone_match = re.search(r"(?:\+?\d[\d ()-]{7,}\d)", text)
    years = [int(value) for value in re.findall(r"(\d{1,2})\+?\s+years?", text, re.I)]
    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
    }
    for word in re.findall(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
        r"\s+years?\b",
        text,
        re.I,
    ):
        years.append(word_numbers[word.lower()])
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return {
        "name": first_line[:100] if first_line else "",
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "years_experience": max(years) if years else 0,
    }
