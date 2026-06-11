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


def raw_log_block(df: pd.DataFrame, max_rows: int = 2000) -> str:
    """Collapsible raw-log table appended to every section."""
    if df is None or df.empty:
        return ""

    total = len(df)
    display = df.head(max_rows)
    truncated = total > max_rows

    cols = [c for c in ("timestamp", "level", "thread", "message") if c in display.columns]

    def _esc(s: str) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    header = "".join(f"<th>{c}</th>" for c in cols)
    rows_html = ""
    for _, row in display.iterrows():
        cells = ""
        for c in cols:
            val = row[c]
            if c == "timestamp" and pd.notna(val):
                val = str(val)[:19]
            elif c == "message":
                val = _esc(str(val))[:600]
                val = f'<span style="white-space:pre-wrap;font-family:monospace;font-size:.75rem">{val}</span>'
            else:
                val = _esc(str(val)) if pd.notna(val) else ""
            cells += f"<td>{val}</td>"
        rows_html += f"<tr>{cells}</tr>"

    note = (
        f'<p style="font-size:.75rem;color:#888;margin:.4rem 0">'
        f'Showing first {max_rows:,} of {total:,} rows.</p>'
    ) if truncated else ""

    return f"""
<details class="raw-log">
  <summary>Raw log &nbsp;<span class="raw-count">{total:,} rows</span></summary>
  {note}
  <div style="overflow-x:auto;max-height:420px;overflow-y:auto;margin-top:.5rem">
    <table class="raw-table">
      <thead><tr>{header}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</details>"""
