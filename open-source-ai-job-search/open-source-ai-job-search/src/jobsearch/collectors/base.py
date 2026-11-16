from __future__ import annotations

from typing import Protocol

from ..models import Job


class Collector(Protocol):
    name: str

    def collect(self) -> list[Job]: ...
