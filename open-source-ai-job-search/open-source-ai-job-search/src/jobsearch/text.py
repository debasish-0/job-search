from __future__ import annotations

import hashlib
import html
import math
import re
from collections import Counter
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlparse


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)

    def get_text(self) -> str:
        return "\n".join(self.parts)


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "we",
    "will",
    "with",
    "you",
    "your",
}


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    decoded = value
    for _ in range(3):
        unescaped = html.unescape(decoded)
        if unescaped == decoded:
            break
        decoded = unescaped
    try:
        parser.feed(decoded)
        parser.close()
        text = parser.get_text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return normalize_whitespace(text)


def normalize_whitespace(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def normalize_key(value: str | None) -> str:
    value = (value or "").lower()
    replacements = {
        "c++": "cplusplus",
        "c#": "csharp",
        ".net": "dotnet",
        "node.js": "nodejs",
        "next.js": "nextjs",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def stable_hash(*parts: str) -> str:
    payload = "|".join(normalize_key(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def slugify(value: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug[:max_length].rstrip("-") or "item")


def tokenize(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9.+#/-]*", value.lower())
    return [token for token in tokens if token not in STOPWORDS and len(token) > 1]


def lexical_cosine(left: str, right: str) -> float:
    left_counts = Counter(tokenize(left))
    right_counts = Counter(tokenize(right))
    if not left_counts or not right_counts:
        return 0.0
    common = set(left_counts).intersection(right_counts)
    numerator = sum(left_counts[token] * right_counts[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, numerator / (left_norm * right_norm)))


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left)
    right_values = list(right)
    if not left_values or len(left_values) != len(right_values):
        return 0.0
    numerator = sum(a * b for a, b in zip(left_values, right_values, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left_values))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(-1.0, min(1.0, numerator / (left_norm * right_norm)))


def contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = f" {normalize_key(text)} "
    normalized_phrase = normalize_key(phrase)
    return bool(normalized_phrase and f" {normalized_phrase} " in normalized_text)


def safe_http_url(value: str | None) -> str:
    url = (value or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return url
