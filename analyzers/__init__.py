"""Analyzer registry."""

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


from analyzers import performance, access, error, dump, engine, dhtml, generic  # noqa: E402

_REGISTRY: dict[str, object] = {}

for _mod in (performance, access, error, dump, engine, dhtml, generic):
    for _lt in _mod.LOG_TYPES:
        _REGISTRY[_lt] = _mod


def get_analyzer(log_type: str) -> Optional[object]:
    return _REGISTRY.get(log_type) or _REGISTRY.get("unknown")
