"""
Performance log analyzer.

Performance.log uses the same format as Engine.log.
Delegates to the engine analyzer but relabels itself.
"""

from __future__ import annotations
from typing import Optional

from log_parser import LogFile
from analyzers.engine import analyze as _engine_analyze
from analyzers._base import section_wrap, no_data_section

LOG_TYPES = ["performance"]


async def analyze(
    lf: LogFile,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> str:
    # Engine analyzer handles elapsed-time extraction and level charts —
    # exactly what performance.log needs.
    return await _engine_analyze(lf, time_from=time_from, time_to=time_to)
