"""
Dump log analyzer — task lifecycle (submit, execute, finish) and task durations.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from log_parser import LogFile
from analyzers._base import (
    apply_time_filter, fig_to_html, stat_card, section_wrap, no_data_section
)

LOG_TYPES = ["dump"]


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
    cards = [stat_card("Total rows", str(len(df)))]
    if "level" in df.columns:
        cards.append(stat_card("Errors", str((df["level"] == "ERROR").sum())))
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    if "timestamp" in df.columns:
        chart = _task_events_chart(df)
        if chart:
            parts.append(chart)

    parts.append(
        '<p class="note" style="font-size:.8rem;color:#888;margin-top:.5rem;">'
        'Tip: share a real dump.log sample to compute task queue depth and latency histograms.'
        '</p>'
    )

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _task_events_chart(df: pd.DataFrame) -> str:
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return ""

    df["minute"] = df["timestamp"].dt.floor("min")
    counts = df.groupby("minute").size().reset_index(name="events")

    fig = go.Figure(go.Bar(
        x=counts["minute"],
        y=counts["events"],
        marker_color="#1a3a5c",
    ))
    fig.update_layout(
        title="Task Events Over Time",
        xaxis_title="Time",
        yaxis_title="Events / minute",
        height=300,
        margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig_to_html(fig)
