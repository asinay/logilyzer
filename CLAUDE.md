# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication style

Always use `/caveman` mode (full intensity) in this repo.

## Commands

```bash
# Create and activate venv (one-time)
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

# Install deps
pip install -r requirements.txt

# Run server (dev)
uvicorn app:app --reload --host 127.0.0.1 --port 8000

# Syntax-check all Python files (no test suite yet)
python -c "import ast, pathlib, sys; errors=[f'ERR {p}: {e}' for p in pathlib.Path('.').rglob('*.py') for e in [None] if not (lambda: (ast.parse(p.read_text()), True)[1])()]; ..."
# Simpler one-liner:
python -m py_compile app.py log_parser.py analyzers/*.py

# Generate sample report without server
python -c "
import asyncio, pathlib
from log_parser import detect_log_type, parse_log_file
from analyzers import get_analyzer
# ... (see outputs/sample_report.html generation pattern in chat history)
"
```

## Architecture

Single-process FastAPI app. No database. Sessions stored in-memory dict in `app.py`.

**Request flow:**
1. `POST /upload` → `log_parser.detect_log_type()` → `log_parser.parse_log_file()` → session stored; returns `server_version` per file (parsed from header blocks) for client-side compat warning
2. `POST /export` → `analyzers.get_analyzer(log_type).analyze(lf, time_from, time_to)` per file (concurrent via `asyncio.gather`) → injects `server_info_block` + `jvm_health_block` + `raw_log_block` → `_build_report()` → HTML file download

**Log format** (critical to understand before editing parser):
- Each entry ends with `[ThreadName][LEVEL][DD MM YYYY HH:MM:SS,mmm optional_tz]`
- Marker is at the **end** of the entry, not the start
- Entries span multiple lines (stack traces, HTTP dumps)
- Files begin with startup header blocks between `====...====` separators — these are skipped

**`log_parser.py`**
- `detect_log_type(filename, text)` — filename-hint lookup only (content hints removed as filename is reliable)
- `parse_log_file()` → `_parse_entries()` walks lines, buffers until trailing marker found, flushes as one row
- Timestamp parsed from `DD MM YYYY HH:MM:SS,mmm` → pandas datetime
- Returns `LogFile` dataclass with `.df` (columns: `timestamp`, `thread`, `level`, `message`)

**`analyzers/`**
- Each module declares `LOG_TYPES: list[str]` and `async def analyze(lf, time_from, time_to) -> str`
- Returns an HTML string (section card with Plotly charts + stat cards)
- `__init__.py` builds a `_REGISTRY` dict and exposes `get_analyzer(log_type)`
- `_base.py` — shared helpers: `apply_time_filter()`, `fig_to_html()`, `stat_card()`, `section_wrap()`
- `performance.py` delegates to `engine.py` (identical log format)

**Analyzer responsibilities by log type:**
| Type | Key extractions |
|------|----------------|
| `dump` | OnDemand/Schedule Running/Queuing/Waiting counters → queue depth charts |
| `engine`/`debug`/`performance` | `ELAPSED:`/`Elapsed(MS):`/`cost=` → timing scatter + thread activity |
| `error` | Exception class grouping, error rate timeline, top messages table |
| `access` | Receive/Responded request patterns, HTTP method distribution, top IPs |
| `dhtml` | `T-S/C-A-*-ActionName ... cost=N` → action cost scatter + perf table |
| `event`/`manage`/`page_report` | Level distribution over time (engine analyzer) |

**`analyzers/jvm_health.py`** — not a log-type analyzer; called directly from `app.py` after each analyzer. Scans `lf.df` messages for JVM signals (OOM, crash markers, deadlock, StackOverflow, GC pressure) and `lf.raw_text` for JVM args. Returns an HTML block or `''` if nothing found. Severity levels: CRITICAL / HIGH / WARN.

**`static/index.html`** — vanilla JS, no build step. Three-step UI: upload → time filter → generate report. Talks to `/upload` and `/export` only. Shows a version compat warning (red alert) when uploaded files contain a server version < V23.

**Adding a new log type:**
1. Add filename hint to `_FILENAME_HINTS` in `log_parser.py`
2. Create `analyzers/<type>.py` with `LOG_TYPES` + `async def analyze(...)`
3. Import it in `analyzers/__init__.py` loop

**`outputs/`** — gitignored, holds generated HTML reports.  
**`sample_logs/`** — gitignored (contents), used for local testing only.  
**`demo/sample_LogiLyzer_report.html`** — pre-generated sample report; served live at `https://asinay.github.io/logilyzer/demo/sample_LogiLyzer_report.html` via GitHub Pages.

**Supported server versions:** V23.x and V25.x. V22 and earlier use a different log format and are not supported. Version is detected from the `====...====` startup header block (`Version: Logi Report Server Vxx.x`).
