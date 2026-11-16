from __future__ import annotations

from ..config import AppConfig
from ..http import HttpJsonClient
from .ashby import AshbyCollector
from .base import Collector
from .greenhouse import GreenhouseCollector
from .lever import LeverCollector
from .local_json import LocalJsonCollector


def build_collectors(config: AppConfig) -> list[Collector]:
    client = HttpJsonClient(
        user_agent=config.app.user_agent,
        timeout_seconds=config.app.request_timeout_seconds,
        delay_seconds=config.app.request_delay_seconds,
    )
    collectors: list[Collector] = []
    for source in config.sources:
        if source.kind == "greenhouse":
            collectors.append(
                GreenhouseCollector(source.identifier, source.company, client)
            )
        elif source.kind == "lever":
            collectors.append(
                LeverCollector(
                    source.identifier,
                    source.company,
                    client,
                    region=source.region,
                )
            )
        elif source.kind == "ashby":
            collectors.append(
                AshbyCollector(
                    source.identifier,
                    source.company,
                    client,
                    include_compensation=source.include_compensation,
                )
            )
        elif source.kind == "local_json":
            collectors.append(LocalJsonCollector(source.identifier, source.company))
    return collectors


__all__ = [
    "AshbyCollector",
    "Collector",
    "GreenhouseCollector",
    "LeverCollector",
    "LocalJsonCollector",
    "build_collectors",
]
