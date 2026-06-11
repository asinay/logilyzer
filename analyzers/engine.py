"""
Engine / Debug log analyzer.

Extracts:
  - ELAPSED: N and Elapsed(MS): N timing values from Timer lines
  - Log level distribution over time
  - Thread activity
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

LOG_TYPES = ["engine", "page_report", "manage", "event", "debug", "performance"]

# Matches lines like:
#   Timer\nLoad <path> ELAPSED: 47
#   CacheableLoader(...) ... Elapsed(MS): 258
#   Something cost=N
_ELAPSED_RE  = re.compile(r"ELAPSED:\s*(\d+)", re.I)
_ELAPSED_MS_RE = re.compile(r"Elapsed\(MS\):\s*(\d+)", re.I)
_COST_RE     = re.compile(r"\bcost=(\d+)")


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

    # Attach elapsed/cost values where present
    df = _extract_timings(df)

    parts: list[str] = []

    # ── Stat cards ──────────────────────────────────────────
    cards = [stat_card("Total entries", str(len(df)))]
    if "level" in df.columns:
        cards.append(stat_card("Errors",   str((df["level"] == "ERROR").sum())))
        cards.append(stat_card("Warnings", str((df["level"] == "WARN").sum())))
    if "elapsed_ms" in df.columns and df["elapsed_ms"].notna().any():
        d = df["elapsed_ms"].dropna()
        cards.append(stat_card("Avg elapsed", f"{d.mean():.0f} ms"))
        cards.append(stat_card("Max elapsed", f"{d.max():.0f} ms"))
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    # ── Elapsed-time scatter over time ──────────────────────
    if "elapsed_ms" in df.columns and df["elapsed_ms"].notna().any():
        t_df = df.dropna(subset=["timestamp", "elapsed_ms"]).sort_values("timestamp")
        if not t_df.empty:
            # try to extract label (filename/path from message)
            t_df = t_df.copy()
            t_df["label"] = t_df["message"].str.extract(r"([\w.-]+\.(?:wls|cat|rpt|rsd))", expand=False)
            fig = go.Figure(go.Scatter(
                x=t_df["timestamp"],
                y=t_df["elapsed_ms"],
                mode="markers",
                marker=dict(size=6, color="#1a3a5c", opacity=0.7),
                text=t_df["label"].fillna(""),
                hovertemplate="%{x}<br>%{y} ms<br>%{text}<extra></extra>",
            ))
            fig.update_layout(
                title="Operation Elapsed Time Over Time",
                xaxis_title="Time", yaxis_title="Elapsed (ms)",
                height=320, margin=dict(l=40, r=20, t=40, b=40),
            )
            parts.append(fig_to_html(fig))

    # ── Log-level stacked bar over time ─────────────────────
    if "level" in df.columns:
        level_chart = _level_chart(df)
        if level_chart:
            parts.append(level_chart)

    # ── Thread activity ──────────────────────────────────────
    if "thread" in df.columns:
        thread_chart = _thread_chart(df)
        if thread_chart:
            parts.append(thread_chart)

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _extract_timings(df: pd.DataFrame) -> pd.DataFrame:
    def _get_ms(msg: str) -> Optional[float]:
        m = _ELAPSED_MS_RE.search(msg)
        if m:
            return float(m.group(1))
        m = _ELAPSED_RE.search(msg)
        if m:
            return float(m.group(1))
        m = _COST_RE.search(msg)
        if m:
            return float(m.group(1))
        return None

    df = df.copy()
    df["elapsed_ms"] = df["message"].apply(_get_ms)
    return df


def _level_chart(df: pd.DataFrame) -> str:
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return ""
    df["minute"] = df["timestamp"].dt.floor("min")
    grp = df.groupby(["minute", "level"]).size().unstack(fill_value=0).reset_index()
    fig = go.Figure()
    for lvl, color in [("ERROR","#dc3545"),("WARN","#fd7e14"),("INFO","#0d6efd"),
                       ("DEBUG","#6c757d"),("TRACE","#adb5bd")]:
        if lvl in grp.columns:
            fig.add_trace(go.Bar(x=grp["minute"], y=grp[lvl], name=lvl, marker_color=color))
    fig.update_layout(
        title="Log Level Distribution Over Time", barmode="stack",
        xaxis_title="Time", yaxis_title="Count/min",
        height=280, margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.3),
    )
    return fig_to_html(fig)


def _thread_chart(df: pd.DataFrame) -> str:
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return ""
    df["minute"] = df["timestamp"].dt.floor("min")
    # Show count of distinct active threads per minute
    active = df.groupby("minute")["thread"].nunique().reset_index(name="threads")
    if active.empty:
        return ""
    fig = go.Figure(go.Scatter(
        x=active["minute"], y=active["threads"],
        mode="lines", fill="tozeroy",
        line=dict(color="#795548"),
    ))
    fig.update_layout(
        title="Active Threads Over Time",
        xaxis_title="Time", yaxis_title="Distinct threads/min",
        height=250, margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig_to_html(fig)
