"""
Dump log analyzer.

Each TRACE line looks like:
  Dumping localhost-processing task counters
  [OnDemand:Running=N; Queuing=N; Waiting=N],
  [Schedule:Running=N; Queuing=N; Waiting=N]

We extract all six counters over time to show queue depth trends.
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

LOG_TYPES = ["dump"]

# Matches the task-counter dump line
_COUNTER_RE = re.compile(
    r"OnDemand:Running=(\d+);\s*Queuing=(\d+);\s*Waiting=(\d+).*?"
    r"Schedule:Running=(\d+);\s*Queuing=(\d+);\s*Waiting=(\d+)"
)


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

    # Extract task counters
    counter_rows = []
    for _, row in df.iterrows():
        m = _COUNTER_RE.search(row.get("message", ""))
        if m and pd.notna(row["timestamp"]):
            counter_rows.append({
                "timestamp":   row["timestamp"],
                "od_running":  int(m.group(1)),
                "od_queuing":  int(m.group(2)),
                "od_waiting":  int(m.group(3)),
                "sc_running":  int(m.group(4)),
                "sc_queuing":  int(m.group(5)),
                "sc_waiting":  int(m.group(6)),
            })

    parts: list[str] = []

    total = len(df)
    cards = [stat_card("Total entries", str(total))]
    if "level" in df.columns:
        cards.append(stat_card("Errors", str((df["level"] == "ERROR").sum())))
    if counter_rows:
        cards.append(stat_card("Counter snapshots", str(len(counter_rows))))

    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    if counter_rows:
        cdf = pd.DataFrame(counter_rows).sort_values("timestamp")

        # On-Demand queue depth chart
        fig = go.Figure()
        for col, name, color in [
            ("od_running", "OnDemand Running", "#1a3a5c"),
            ("od_queuing", "OnDemand Queuing", "#2196f3"),
            ("od_waiting", "OnDemand Waiting", "#90caf9"),
        ]:
            fig.add_trace(go.Scatter(
                x=cdf["timestamp"], y=cdf[col],
                mode="lines", name=name,
                line=dict(color=color),
                stackgroup="od",
            ))
        fig.update_layout(
            title="OnDemand Task Queue Depth Over Time",
            xaxis_title="Time", yaxis_title="Tasks",
            height=300, margin=dict(l=40, r=20, t=40, b=40),
            legend=dict(orientation="h", y=-0.3),
        )
        parts.append(fig_to_html(fig))

        # Scheduled queue depth chart
        fig2 = go.Figure()
        for col, name, color in [
            ("sc_running", "Schedule Running", "#1b5e20"),
            ("sc_queuing", "Schedule Queuing", "#4caf50"),
            ("sc_waiting", "Schedule Waiting", "#a5d6a7"),
        ]:
            fig2.add_trace(go.Scatter(
                x=cdf["timestamp"], y=cdf[col],
                mode="lines", name=name,
                line=dict(color=color),
                stackgroup="sc",
            ))
        fig2.update_layout(
            title="Scheduled Task Queue Depth Over Time",
            xaxis_title="Time", yaxis_title="Tasks",
            height=300, margin=dict(l=40, r=20, t=40, b=40),
            legend=dict(orientation="h", y=-0.3),
        )
        parts.append(fig_to_html(fig2))
    else:
        parts.append("<p>No task-counter lines found in this time range.</p>")

    # Level timeline
    if "level" in df.columns:
        parts.append(_level_chart(df))

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _level_chart(df: pd.DataFrame) -> str:
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return ""
    df["minute"] = df["timestamp"].dt.floor("min")
    grp = df.groupby(["minute", "level"]).size().unstack(fill_value=0).reset_index()
    fig = go.Figure()
    for lvl, color in [("ERROR","#dc3545"),("WARN","#fd7e14"),("TRACE","#adb5bd"),("DEBUG","#6c757d")]:
        if lvl in grp.columns:
            fig.add_trace(go.Bar(x=grp["minute"], y=grp[lvl], name=lvl, marker_color=color))
    fig.update_layout(
        title="Log Level Distribution", barmode="stack",
        xaxis_title="Time", yaxis_title="Count/min",
        height=250, margin=dict(l=40,r=20,t=40,b=40),
        legend=dict(orientation="h", y=-0.3),
    )
    return fig_to_html(fig)
