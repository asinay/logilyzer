"""
Analyzer registry.

Each analyzer module exposes an async `analyze(lf, time_from, time_to) -> str`
and a list of `LOG_TYPES` it handles.
"""

from __future__ import annotations
from typing import Optional, Protocol

from log_parser import LogFile


class Analyzer(Protocol):
    LOG_TYPES: list[str]

    async def analyze(
        self,
        lf: LogFile,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> str: ...


# Import all analyzers so they register themselves
from analyzers import performance, access, error, dump, engine, generic  # noqa: E402

_REGISTRY: dict[str, "Analyzer"] = {}

for _mod in (performance, access, error, dump, engine, generic):
    for _lt in _mod.LOG_TYPES:
        _REGISTRY[_lt] = _mod  # type: ignore[assignment]


def get_analyzer(log_type: str) -> Optional["Analyzer"]:
    return _REGISTRY.get(log_type) or _REGISTRY.get("unknown")
