"""
Error log analyzer.

Extracts:
  - Error / warning rate over time (stacked area)
  - Exception class grouping (first line of stack trace pattern)
  - Top error messages (deduplicated)
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from log_parser import LogFile
from analyzers._base import (
    apply_time_filter, fig_to_html, stat_card, section_wrap, no_data_section
)

LOG_TYPES = ["error"]

# Java exception class: e.g. jet.exception.InvalidParameterException or java.sql.SQLException
_EXCEPTION_RE = re.compile(r"^([\w$.]+Exception|[\w$.]+Error)(?::\s|$)", re.MULTILINE)


async def analyze(
    lf: LogFile,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> str:
    if not lf.has_data:
        return no_data_section(lf.filename, lf.log_type)

    df = apply_time_filter(lf.df.copy(), time_from, time_to)
    if df.empty:
        return no_data_section(lf.filename, lf.log_type, "No data in the selected time range.")

    parts: list[str] = []

    # ── Stat cards ──────────────────────────────────────────
    total = len(df)
    errors = (df["level"] == "ERROR").sum() if "level" in df.columns else 0
    warns  = (df["level"] == "WARN").sum()  if "level" in df.columns else 0
    fatals = (df["level"] == "FATAL").sum() if "level" in df.columns else 0
    cards = [
        stat_card("Total entries", str(total)),
        stat_card("Errors",   str(errors)),
        stat_card("Warnings", str(warns)),
    ]
    if fatals:
        cards.append(stat_card("Fatal", str(fatals)))
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    # ── Error/warn rate over time ────────────────────────────
    if "timestamp" in df.columns:
        rate_chart = _rate_chart(df)
        if rate_chart:
            parts.append(rate_chart)

    # ── Exception class breakdown ────────────────────────────
    exc_chart = _exception_chart(df)
    if exc_chart:
        parts.append(exc_chart)

    # ── Top error messages table ─────────────────────────────
    parts.append(_top_errors_table(df))

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _rate_chart(df: pd.DataFrame) -> str:
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return ""
    df["minute"] = df["timestamp"].dt.floor("min")
    grp = df.groupby(["minute", "level"]).size().unstack(fill_value=0).reset_index()

    fig = go.Figure()
    for lvl, color in [("FATAL","#6f0000"),("ERROR","#dc3545"),("WARN","#fd7e14")]:
        if lvl in grp.columns:
            fig.add_trace(go.Scatter(
                x=grp["minute"], y=grp[lvl], name=lvl,
                mode="lines", line=dict(color=color),
                fill="tozeroy", stackgroup="one",
            ))
    fig.update_layout(
        title="Error / Warning Rate Over Time",
        xaxis_title="Time", yaxis_title="Count/min",
        height=300, margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.3),
    )
    return fig_to_html(fig)


def _exception_chart(df: pd.DataFrame) -> str:
    if "message" not in df.columns:
        return ""
    err_df = df[df["level"].isin(["ERROR","WARN","FATAL"])] if "level" in df.columns else df
    if err_df.empty:
        return ""

    exc_classes = err_df["message"].str.extract(_EXCEPTION_RE, expand=False).dropna()
    if exc_classes.empty:
        return ""

    # Shorten class names: keep last two parts
    exc_classes = exc_classes.apply(lambda s: ".".join(s.rsplit(".", 2)[-2:]) if "." in s else s)
    counts = exc_classes.value_counts().head(10)

    fig = go.Figure(go.Bar(
        y=counts.index.tolist()[::-1],
        x=counts.values.tolist()[::-1],
        orientation="h",
        marker_color="#1a3a5c",
    ))
    fig.update_layout(
        title="Top Exception Types",
        xaxis_title="Count",
        height=max(200, len(counts) * 30 + 80),
        margin=dict(l=180, r=20, t=40, b=40),
    )
    return fig_to_html(fig)


def _top_errors_table(df: pd.DataFrame) -> str:
    if "message" not in df.columns:
        return ""
    err_df = df[df["level"].isin(["ERROR","WARN","FATAL"])] if "level" in df.columns else df
    if err_df.empty:
        return "<p>No errors or warnings found.</p>"

    # First line of message only for grouping
    first_lines = err_df["message"].str.split("\n").str[0].str.strip().str[:120]
    top = first_lines.value_counts().head(15).reset_index()
    top.columns = ["message", "count"]

    rows_html = "".join(
        f"<tr><td style='font-family:monospace;font-size:.8rem;padding:.3rem .5rem'>"
        f"{_esc(row['message'])}</td>"
        f"<td style='text-align:right;padding:.3rem .75rem;white-space:nowrap'>{row['count']}</td></tr>"
        for _, row in top.iterrows()
    )
    return (
        "<h3 style='font-size:.9rem;margin:1rem 0 .5rem'>Top Error Messages</h3>"
        "<div style='overflow-x:auto'>"
        "<table style='width:100%;border-collapse:collapse;font-size:.85rem'>"
        "<thead><tr style='border-bottom:2px solid #dee2e6'>"
        "<th style='text-align:left;padding:.3rem .5rem'>Message (first line, truncated)</th>"
        "<th style='text-align:right;padding:.3rem .75rem'>Count</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table></div>"
    )


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
