"""
Log type detection and parsing for Logi Report log files.

Logi Report log categories:
  engine      - report execution and export events
  page_report - page report / ad-hoc events
  access      - user logins, task scheduling
  manage      - server console / config changes
  error       - error events across all categories
  event       - server lifecycle (start / stop)
  debug       - SQL statements, debug traces
  performance - report/export timing
  dump        - task lifecycle (submit, execute, finish)
  unknown     - unrecognised format
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class LogFile:
    filename: str
    log_type: str
    raw_text: str
    df: Optional[pd.DataFrame] = field(default=None, repr=False)

    @property
    def row_count(self) -> int:
        return len(self.df) if self.df is not None else 0

    @property
    def has_data(self) -> bool:
        return self.df is not None and not self.df.empty

    @property
    def time_min(self) -> Optional[str]:
        if self.df is not None and "timestamp" in self.df.columns and not self.df.empty:
            ts = self.df["timestamp"].dropna()
            if not ts.empty:
                return str(ts.min())
        return None

    @property
    def time_max(self) -> Optional[str]:
        if self.df is not None and "timestamp" in self.df.columns and not self.df.empty:
            ts = self.df["timestamp"].dropna()
            if not ts.empty:
                return str(ts.max())
        return None


# ---------------------------------------------------------------------------
# Log type detection
# ---------------------------------------------------------------------------

# Maps filename substrings (lower-case) to log type
_FILENAME_HINTS: list[tuple[str, str]] = [
    ("performance", "performance"),
    ("perf",        "performance"),
    ("access",      "access"),
    ("error",       "error"),
    ("engine",      "engine"),
    ("page",        "page_report"),
    ("manage",      "manage"),
    ("event",       "event"),
    ("debug",       "debug"),
    ("dump",        "dump"),
]

# Patterns in the first ~2 KB of file content
_CONTENT_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bReportExecutionTime\b", re.I),  "performance"),
    (re.compile(r"\bExportTime\b", re.I),           "performance"),
    (re.compile(r"\bUserLogin\b|\bUserLogout\b", re.I), "access"),
    (re.compile(r"\bScheduleTask\b|\bRunTask\b", re.I), "access"),
    (re.compile(r"\bERROR\b.*\bException\b"),        "error"),
    (re.compile(r"\bServerStarted\b|\bServerStopped\b", re.I), "event"),
    (re.compile(r"\bSELECT\b.*\bFROM\b"),           "debug"),
    (re.compile(r"\bTaskSubmit\b|\bTaskFinish\b", re.I), "dump"),
]


def detect_log_type(filename: str, text: str) -> str:
    fname_lower = filename.lower()
    for hint, log_type in _FILENAME_HINTS:
        if hint in fname_lower:
            return log_type

    sample = text[:4096]
    for pattern, log_type in _CONTENT_HINTS:
        if pattern.search(sample):
            return log_type

    return "unknown"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Common Logi Report timestamp patterns (add more as real samples arrive)
_TIMESTAMP_PATTERNS: list[str] = [
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?",   # 2024-03-15 14:23:01,234
    r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}",              # 2024/03/15 14:23:01
    r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}",              # 03/15/2024 14:23:01
    r"\d{2}-\w{3}-\d{4} \d{2}:\d{2}:\d{2}",              # 15-Mar-2024 14:23:01
]
_TS_RE = re.compile("|".join(_TIMESTAMP_PATTERNS))


def parse_log_file(filename: str, log_type: str, text: str) -> LogFile:
    """Parse log text into a LogFile with a DataFrame of structured rows."""
    df = _try_structured_parse(log_type, text)
    if df is None:
        df = _generic_line_parse(text)
    return LogFile(filename=filename, log_type=log_type, raw_text=text, df=df)


def _try_structured_parse(log_type: str, text: str) -> Optional[pd.DataFrame]:
    """
    Attempt log-type-specific parsing.
    Returns a DataFrame or None if the format isn't recognised yet.
    Each log-type parser should at minimum produce a 'timestamp' column
    (as a pandas datetime) and a 'level' column where available.
    """
    # Placeholder: real parsers will be added once sample files are available.
    # For now fall through to the generic parser for all types.
    return None


def _generic_line_parse(text: str) -> pd.DataFrame:
    """
    Fallback: scan every line for a timestamp and capture the whole line.
    Produces columns: timestamp, level, message
    """
    rows = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue
        m = _TS_RE.search(line)
        ts_str = m.group(0) if m else None
        ts = _parse_timestamp(ts_str) if ts_str else pd.NaT
        level = _extract_level(line)
        rows.append({"timestamp": ts, "level": level, "message": line})

    if not rows:
        return pd.DataFrame(columns=["timestamp", "level", "message"])

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def _parse_timestamp(ts_str: str) -> Optional[str]:
    # Normalise common separators so pandas can parse them
    ts_str = ts_str.replace(",", ".").replace("/", "-")
    return ts_str


def _extract_level(line: str) -> str:
    for lvl in ("ERROR", "WARN", "INFO", "DEBUG", "FATAL", "TRACE"):
        if lvl in line.upper():
            return lvl
    return "INFO"
