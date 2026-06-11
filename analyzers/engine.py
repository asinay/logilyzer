"""
Engine log analyzer — report execution and export events.
Handles: engine, page_report, manage, event, debug
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from log_parser import LogFile
from analyzers._base import (
    apply_time_filter, fig_to_html, stat_card, section_wrap, no_data_section
)

LOG_TYPES = ["engine", "page_report", "manage", "event", "debug"]


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
        cards.append(stat_card("Warnings", str((df["level"] == "WARN").sum())))
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    if "timestamp" in df.columns and "level" in df.columns:
        chart = _level_chart(df, lf.log_type)
        if chart:
            parts.append(chart)

    parts.append(
        '<p class="note" style="font-size:.8rem;color:#888;margin-top:.5rem;">'
        f'Tip: share a real {lf.log_type}.log sample to unlock dedicated analysis.'
        '</p>'
    )

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _level_chart(df: pd.DataFrame, log_type: str) -> str:
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return ""

    df["minute"] = df["timestamp"].dt.floor("min")
    grp = df.groupby(["minute", "level"]).size().unstack(fill_value=0).reset_index()

    fig = go.Figure()
    color_map = {"ERROR": "#dc3545", "WARN": "#fd7e14", "INFO": "#0d6efd", "DEBUG": "#6c757d"}
    for lvl in ("ERROR", "WARN", "INFO", "DEBUG"):
        if lvl in grp.columns:
            fig.add_trace(go.Bar(
                x=grp["minute"], y=grp[lvl], name=lvl,
                marker_color=color_map.get(lvl, "#888"),
            ))

    fig.update_layout(
        title=f"Log Levels Over Time — {log_type}",
        barmode="stack",
        xaxis_title="Time",
        yaxis_title="Count / minute",
        height=300,
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.25),
    )
    return fig_to_html(fig)
