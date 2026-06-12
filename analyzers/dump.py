"""
Dump log analyzer.

Each snapshot entry looks like:
  TaskManager status dump:
  OnDemand:Running=6,Queuing=9,Waiting=1
  Schedule:Running=0,Queuing=1,Waiting=3

Separators can be commas or semicolons depending on server version.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from log_parser import LogFile
from analyzers._base import (
    apply_time_filter, fig_to_html, stat_card, section_wrap, no_data_section
)

LOG_TYPES = ["dump"]

_COUNTER_RE = re.compile(
    r"OnDemand:Running=(\d+)[,;]\s*Queuing=(\d+)[,;]\s*Waiting=(\d+).*?"
    r"Schedule:Running=(\d+)[,;]\s*Queuing=(\d+)[,;]\s*Waiting=(\d+)",
    re.DOTALL,
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

    counter_rows = []
    for _, row in df.iterrows():
        m = _COUNTER_RE.search(row.get("message", ""))
        if m and pd.notna(row["timestamp"]):
            counter_rows.append({
                "timestamp":  row["timestamp"],
                "od_running": int(m.group(1)),
                "od_queuing": int(m.group(2)),
                "od_waiting": int(m.group(3)),
                "sc_running": int(m.group(4)),
                "sc_queuing": int(m.group(5)),
                "sc_waiting": int(m.group(6)),
            })

    parts: list[str] = []

    if not counter_rows:
        cards = [
            stat_card("Total entries", str(len(df))),
            stat_card("Counter snapshots", "0"),
        ]
        parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')
        parts.append("<p class='no-data'>No task-counter lines matched in this time range.</p>")
        return section_wrap(lf.filename, lf.log_type, "\n".join(parts))

    cdf = pd.DataFrame(counter_rows).sort_values("timestamp").reset_index(drop=True)
    cdf["od_total"] = cdf["od_running"] + cdf["od_queuing"] + cdf["od_waiting"]
    cdf["sc_total"] = cdf["sc_running"] + cdf["sc_queuing"] + cdf["sc_waiting"]
    cdf["total"]    = cdf["od_total"] + cdf["sc_total"]

    # ── Stat cards ──────────────────────────────────────────────
    peak_row = cdf.loc[cdf["total"].idxmax()]
    cards = [
        stat_card("Snapshots",           str(len(cdf))),
        stat_card("Peak total tasks",     str(int(peak_row["total"]))),
        stat_card("Peak OD queuing",      str(int(cdf["od_queuing"].max()))),
        stat_card("Peak OD running",      str(int(cdf["od_running"].max()))),
        stat_card("Peak sched queuing",   str(int(cdf["sc_queuing"].max()))),
        stat_card("Avg OD total",         f'{cdf["od_total"].mean():.1f}'),
    ]
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    # ── Chart 1: total load overview (OnDemand vs Schedule) ─────
    parts.append(_overview_chart(cdf))

    # ── Chart 2 & 3: stacked breakdown per type ─────────────────
    parts.append(_breakdown_charts(cdf))

    # ── Peak pressure table ──────────────────────────────────────
    parts.append(_peak_table(cdf))

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _overview_chart(cdf: pd.DataFrame) -> str:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cdf["timestamp"], y=cdf["od_total"],
        mode="lines", name="OnDemand total",
        line=dict(color="#0ea5e9", width=2),
        fill="tozeroy", fillcolor="rgba(14,165,233,.12)",
    ))
    fig.add_trace(go.Scatter(
        x=cdf["timestamp"], y=cdf["sc_total"],
        mode="lines", name="Schedule total",
        line=dict(color="#10b981", width=2),
        fill="tozeroy", fillcolor="rgba(16,185,129,.10)",
    ))
    fig.add_trace(go.Scatter(
        x=cdf["timestamp"], y=cdf["total"],
        mode="lines", name="Combined total",
        line=dict(color="#6366f1", width=1.5, dash="dot"),
    ))
    fig.update_layout(
        title="Task Queue Load Over Time",
        xaxis_title="Time", yaxis_title="Active tasks",
        height=320, margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.3),
        hovermode="x unified",
    )
    return fig_to_html(fig)


def _breakdown_charts(cdf: pd.DataFrame) -> str:
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("OnDemand breakdown", "Schedule breakdown"),
        shared_yaxes=False,
    )

    # OnDemand — stacked area
    for col, name, color in [
        ("od_running", "Running", "#0369a1"),
        ("od_queuing", "Queuing", "#0ea5e9"),
        ("od_waiting", "Waiting", "#bae6fd"),
    ]:
        fig.add_trace(go.Scatter(
            x=cdf["timestamp"], y=cdf[col],
            mode="lines", name=name,
            line=dict(color=color, width=1.2),
            stackgroup="od",
            legendgroup=name,
            showlegend=True,
        ), row=1, col=1)

    # Schedule — stacked area
    for col, name, color in [
        ("sc_running", "Running", "#065f46"),
        ("sc_queuing", "Queuing", "#10b981"),
        ("sc_waiting", "Waiting", "#a7f3d0"),
    ]:
        fig.add_trace(go.Scatter(
            x=cdf["timestamp"], y=cdf[col],
            mode="lines", name=name,
            line=dict(color=color, width=1.2),
            stackgroup="sc",
            legendgroup=name,
            showlegend=False,
        ), row=1, col=2)

    fig.update_layout(
        height=300,
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", y=-0.25),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Tasks", row=1, col=1)
    return fig_to_html(fig)


def _peak_table(cdf: pd.DataFrame) -> str:
    top = cdf.nlargest(10, "total")[
        ["timestamp", "od_running", "od_queuing", "od_waiting",
         "sc_running", "sc_queuing", "sc_waiting", "total"]
    ].copy()

    def _td(v, bold=False):
        s = f"<strong>{v}</strong>" if bold else str(v)
        return f"<td style='padding:.3rem .55rem;text-align:right'>{s}</td>"

    rows_html = ""
    for _, r in top.iterrows():
        ts_str = str(r["timestamp"])[:19]
        total  = int(r["total"])
        rows_html += (
            f"<tr>"
            f"<td style='padding:.3rem .55rem;white-space:nowrap;font-family:monospace;font-size:.8rem'>{ts_str}</td>"
            f"{_td(int(r['od_running']))}{_td(int(r['od_queuing']))}{_td(int(r['od_waiting']))}"
            f"{_td(int(r['sc_running']))}{_td(int(r['sc_queuing']))}{_td(int(r['sc_waiting']))}"
            f"{_td(total, bold=True)}"
            f"</tr>"
        )

    th = "<th style='padding:.3rem .55rem;text-align:right;font-size:.75rem;color:#64748b;border-bottom:2px solid #e2e8f0'>"
    th_left = "<th style='padding:.3rem .55rem;text-align:left;font-size:.75rem;color:#64748b;border-bottom:2px solid #e2e8f0'>"
    header = (
        f"{th_left}Timestamp</th>"
        f"{th}OD Run</th>{th}OD Queue</th>{th}OD Wait</th>"
        f"{th}SC Run</th>{th}SC Queue</th>{th}SC Wait</th>"
        f"{th}Total</th>"
    )

    return (
        "<h3 style='font-size:.9rem;margin:1.25rem 0 .5rem'>Peak pressure snapshots (top 10)</h3>"
        "<div style='overflow-x:auto'>"
        "<table style='border-collapse:collapse;font-size:.82rem;width:100%'>"
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )
