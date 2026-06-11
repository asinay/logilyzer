"""Shared helpers for all analyzers."""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


def apply_time_filter(
    df: pd.DataFrame,
    time_from: Optional[str],
    time_to: Optional[str],
) -> pd.DataFrame:
    if "timestamp" not in df.columns or df.empty:
        return df
    if time_from:
        df = df[df["timestamp"] >= pd.to_datetime(time_from, errors="coerce")]
    if time_to:
        df = df[df["timestamp"] <= pd.to_datetime(time_to, errors="coerce")]
    return df


def fig_to_html(fig: go.Figure) -> str:
    return pio.to_html(fig, full_html=False, include_plotlyjs="cdn", config={"responsive": True})


def stat_card(label: str, value: str) -> str:
    return (
        f'<div class="stat-card">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'</div>'
    )


def _section_id(title: str) -> str:
    return "sec-" + "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")


def section_wrap(title: str, badge: str, body: str) -> str:
    sid = _section_id(title)
    return (
        f'<div class="section" id="{sid}">'
        f'<h2>{title} <span class="badge">{badge}</span></h2>'
        f'{body}'
        f'</div>'
    )


def no_data_section(filename: str, log_type: str, reason: str = "") -> str:
    msg = reason or "No time-series data could be extracted from this file."
    return section_wrap(
        filename, log_type,
        f'<p class="no-data">{msg}</p>'
    )


_raw_table_counter = [0]


def raw_log_block(df: pd.DataFrame, max_rows: int = 2000) -> str:
    """Collapsible raw-log table with per-table thread filter."""
    if df is None or df.empty:
        return ""

    _raw_table_counter[0] += 1
    table_id = f"raw-tbl-{_raw_table_counter[0]}"

    total = len(df)
    display = df.head(max_rows)
    truncated = total > max_rows

    cols = [c for c in ("timestamp", "level", "thread", "message") if c in display.columns]

    def _esc(s: str) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Unique threads for the local dropdown
    threads = sorted(display["thread"].dropna().unique().tolist()) if "thread" in display.columns else []
    thread_opts = '<option value="">All threads</option>' + "".join(
        f'<option value="{_esc(t)}">{_esc(t)}</option>' for t in threads
    )
    thread_select = (
        f'<select class="raw-thread-select" data-table="{table_id}" onchange="applyFilters()">'
        f'{thread_opts}</select>'
    ) if threads else ""

    header = "".join(
        f'<th data-col="{i}" onclick="sortTable(\'{table_id}\',{i})">'
        f'{c}<span class="sort-icon">⇅</span></th>'
        for i, c in enumerate(cols)
    )
    rows_html = ""
    for _, row in display.iterrows():
        lvl    = _esc(str(row["level"]))   if "level"  in cols and pd.notna(row.get("level"))  else ""
        thread = _esc(str(row["thread"])) if "thread" in cols and pd.notna(row.get("thread")) else ""
        cells = ""
        for c in cols:
            val = row[c]
            if c == "timestamp" and pd.notna(val):
                val = str(val)[:19]
            elif c == "message":
                val = _esc(str(val))[:600]
                val = f'<span style="white-space:pre-wrap">{val}</span>'
            else:
                val = _esc(str(val)) if pd.notna(val) else ""
            cells += f"<td>{val}</td>"
        rows_html += f'<tr data-level="{lvl}" data-thread="{thread}">{cells}</tr>'

    note = (
        f'<p class="raw-note">Showing first {max_rows:,} of {total:,} rows.</p>'
    ) if truncated else ""

    return f"""
<details class="raw-log">
  <summary>Raw log &nbsp;<span class="raw-count">{total:,} rows</span></summary>
  <div class="raw-toolbar">
    {thread_select}
    <input type="search" class="raw-search" data-table="{table_id}"
           placeholder="Search this table…" oninput="applyFilters()">
    <span class="raw-match-count" id="{table_id}-count"></span>
  </div>
  {note}
  <div class="raw-scroll">
    <table class="raw-table" id="{table_id}">
      <thead><tr>{header}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</details>"""
