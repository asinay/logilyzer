"""
Error log analyzer — surfaces error frequency, top error messages, timeline.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from log_parser import LogFile
from analyzers._base import (
    apply_time_filter, fig_to_html, stat_card, section_wrap, no_data_section
)

LOG_TYPES = ["error"]


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

    total = len(df)
    errors = (df["level"] == "ERROR").sum() if "level" in df.columns else total
    warns = (df["level"] == "WARN").sum() if "level" in df.columns else 0

    cards = [
        stat_card("Total rows", str(total)),
        stat_card("Errors", str(errors)),
        stat_card("Warnings", str(warns)),
    ]
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    # Error rate over time
    if "timestamp" in df.columns:
        chart = _error_timeline(df)
        if chart:
            parts.append(chart)

    # Top error messages table
    if "message" in df.columns:
        parts.append(_top_errors_table(df))

    parts.append(
        '<p class="note" style="font-size:.8rem;color:#888;margin-top:.5rem;">'
        'Tip: share a real error.log sample to improve message deduplication.'
        '</p>'
    )

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _error_timeline(df: pd.DataFrame) -> str:
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return ""

    df["minute"] = df["timestamp"].dt.floor("min")
    grp = df.groupby(["minute", "level"]).size().unstack(fill_value=0).reset_index()

    fig = go.Figure()
    for lvl, color in [("ERROR", "#dc3545"), ("WARN", "#fd7e14")]:
        if lvl in grp.columns:
            fig.add_trace(go.Scatter(
                x=grp["minute"], y=grp[lvl],
                mode="lines", name=lvl,
                line=dict(color=color),
                fill="tozeroy",
                stackgroup="one",
            ))

    fig.update_layout(
        title="Error / Warning Rate Over Time",
        xaxis_title="Time",
        yaxis_title="Count / minute",
        height=300,
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.25),
    )
    return fig_to_html(fig)


def _top_errors_table(df: pd.DataFrame) -> str:
    if "level" in df.columns:
        err_df = df[df["level"].isin(["ERROR", "WARN"])]
    else:
        err_df = df

    if err_df.empty:
        return "<p>No errors found.</p>"

    top = (
        err_df["message"]
        .str[:120]
        .value_counts()
        .head(10)
        .reset_index()
        .rename(columns={"index": "message", "message": "count", "count": "count"})
    )
    # pandas 2.x value_counts returns different column names
    if "count" not in top.columns:
        top.columns = ["message", "count"]

    rows = "".join(
        f"<tr><td style='font-family:monospace;font-size:.8rem'>{row['message']}</td>"
        f"<td style='text-align:right;padding-left:1rem'>{row['count']}</td></tr>"
        for _, row in top.iterrows()
    )
    return (
        "<h3 style='font-size:.9rem;margin-top:1rem'>Top Error Messages</h3>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<thead><tr><th style='text-align:left'>Message (truncated)</th>"
        "<th style='text-align:right'>Count</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
