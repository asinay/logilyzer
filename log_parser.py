"""
Parser for Logi Report log files.

Log entry format (Logi Report TTCC variant):
  <message text...possibly multi-line> [ThreadName][LEVEL][DD MM YYYY HH:MM:SS,mmm optional_tz]

The [thread][level][timestamp] marker always appears at the END of each entry.
Entries can span multiple lines.  Startup header blocks (between === lines) are skipped.

Supported log types (detected from filename):
  engine, page_report, access, manage, error, event, debug, dump, performance, dhtml, unknown
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
                return ts.min().isoformat(sep=" ", timespec="seconds")
        return None

    @property
    def time_max(self) -> Optional[str]:
        if self.df is not None and "timestamp" in self.df.columns and not self.df.empty:
            ts = self.df["timestamp"].dropna()
            if not ts.empty:
                return ts.max().isoformat(sep=" ", timespec="seconds")
        return None


# ---------------------------------------------------------------------------
# Log type detection
# ---------------------------------------------------------------------------

_FILENAME_HINTS: list[tuple[str, str]] = [
    ("performance", "performance"),
    ("perf",        "performance"),
    ("access",      "access"),
    ("error",       "error"),
    ("engine",      "engine"),
    ("dhtml",       "dhtml"),
    ("page",        "page_report"),
    ("manage",      "manage"),
    ("event",       "event"),
    ("debug",       "debug"),
    ("dump",        "dump"),
]


def detect_log_type(filename: str, text: str) -> str:
    fname_lower = filename.lower()
    for hint, log_type in _FILENAME_HINTS:
        if hint in fname_lower:
            return log_type
    return "unknown"


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

# Matches the trailing marker: [ThreadName][LEVEL][DD MM YYYY HH:MM:SS,mmm optional_tz]
# Captures: thread, level, timestamp_str
_MARKER_RE = re.compile(
    r"\[([^\]]+)\]"                      # [ThreadName]
    r"\[(TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\]"  # [LEVEL]
    r"\[(\d{2} \d{2} \d{4} \d{2}:\d{2}:\d{2},\d+)"  # [DD MM YYYY HH:MM:SS,mmm
    r"(?:\s+[^\]]+)?"                    # optional timezone/offset
    r"\]"                                # ]
)

# Startup section separator
_SEP_RE = re.compile(r"^={4,}.+={4,}$")


def parse_log_file(filename: str, log_type: str, text: str) -> LogFile:
    rows = _parse_entries(text)
    if not rows:
        return LogFile(filename=filename, log_type=log_type, raw_text=text,
                       df=pd.DataFrame(columns=["timestamp", "thread", "level", "message"]))

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(
        df["timestamp_str"].str.replace(",", "."),
        format="%d %m %Y %H:%M:%S.%f",
        errors="coerce",
    )
    df.drop(columns=["timestamp_str"], inplace=True)
    df.sort_values("timestamp", inplace=True, ignore_index=True)
    return LogFile(filename=filename, log_type=log_type, raw_text=text, df=df)


def _parse_entries(text: str) -> list[dict]:
    """
    Walk lines building up a message buffer.  When we encounter a marker,
    flush the buffer + marker as one entry.
    """
    rows: list[dict] = []
    buf: list[str] = []
    in_header = False

    for line in text.splitlines():
        # Skip startup header blocks (between ===...=== separators)
        if _SEP_RE.match(line.strip()):
            in_header = True
            buf.clear()
            continue

        if in_header:
            # Header ends at the first marker line
            m = _MARKER_RE.search(line)
            if m and m.end() >= len(line.rstrip()) - 1:
                in_header = False
                # The header entry itself (usually empty message) — skip it
                buf.clear()
            continue

        m = _MARKER_RE.search(line)
        if m and m.end() >= len(line.rstrip()) - 1:
            # This line ends with a marker — the message is everything before it
            msg_on_this_line = line[:m.start()].strip()
            buf.append(msg_on_this_line)
            message = "\n".join(l for l in buf if l).strip()
            rows.append({
                "timestamp_str": m.group(3),
                "thread": m.group(1),
                "level": m.group(2),
                "message": message,
            })
            buf = []
        else:
            buf.append(line.rstrip())

    return rows
