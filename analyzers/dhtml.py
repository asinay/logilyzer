"""
DHTML log analyzer.

DHTML entries trace client-server action round-trips. Key patterns:
  T-S-A-00000000-<Action> ... cost=N
  T-C-A-00000000-<Action> ... cost=N bytes=N
  T-C-ClientContext.checkLogin session=... status=N

Extracts:
  - Action cost (ms) over time
  - Top slowest actions
  - Action type distribution
  - Session activity
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

LOG_TYPES = ["dhtml"]

# T-S-A-00000000-ActionName or T-C-A-...
_ACTION_RE   = re.compile(r"T-[SC]-[AB]-\w+-(\w+)\s+session=\S+.*?\bcost=(\d+)")
_BYTES_RE    = re.compile(r"\bbytes=(\d+)")
_SESSION_RE  = re.compile(r"session=([A-F0-9]+):\d+")


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

    df = _enrich(df)
    parts: list[str] = []

    # ── Stat cards ──────────────────────────────────────────
    total = len(df)
    actions = df["action"].notna().sum() if "action" in df.columns else 0
    sessions = df["session"].nunique() if "session" in df.columns else 0
    cards = [
        stat_card("Total entries", str(total)),
        stat_card("Actions traced", str(int(actions))),
        stat_card("Unique sessions", str(int(sessions))),
    ]
    if "cost_ms" in df.columns and df["cost_ms"].notna().any():
        d = df["cost_ms"].dropna()
        cards.append(stat_card("Avg cost", f"{d.mean():.0f} ms"))
        cards.append(stat_card("Max cost", f"{d.max():.0f} ms"))
    if "level" in df.columns:
        cards.append(stat_card("Errors", str((df["level"] == "ERROR").sum())))
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    # ── Action cost over time ────────────────────────────────
    if "cost_ms" in df.columns and df["cost_ms"].notna().any():
        parts.append(_cost_chart(df))

    # ── Top slowest actions ──────────────────────────────────
    if "action" in df.columns and actions > 0:
        parts.append(_slowest_table(df))

    # ── Log level distribution ───────────────────────────────
    if "level" in df.columns:
        parts.append(_level_chart(df))

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["action"]  = pd.NA
    df["cost_ms"] = pd.NA
    df["bytes"]   = pd.NA
    df["session"] = pd.NA

    for idx, row in df.iterrows():
        msg = row.get("message", "") or ""
        m = _ACTION_RE.search(msg)
        if m:
            df.at[idx, "action"]  = m.group(1)
            df.at[idx, "cost_ms"] = float(m.group(2))
            bm = _BYTES_RE.search(msg)
            if bm:
                df.at[idx, "bytes"] = float(bm.group(1))
        sm = _SESSION_RE.search(msg)
        if sm:
            df.at[idx, "session"] = sm.group(1)

    return df


def _cost_chart(df: pd.DataFrame) -> str:
    t_df = df.dropna(subset=["timestamp", "cost_ms"]).sort_values("timestamp")
    if t_df.empty:
        return ""
    fig = go.Figure(go.Scatter(
        x=t_df["timestamp"],
        y=t_df["cost_ms"],
        mode="markers",
        marker=dict(size=5, color="#1a3a5c", opacity=0.6),
        text=t_df["action"].fillna(""),
        hovertemplate="%{x}<br>cost: %{y} ms<br>action: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title="Action Cost Over Time",
        xaxis_title="Time", yaxis_title="Cost (ms)",
        height=320, margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig_to_html(fig)


def _slowest_table(df: pd.DataFrame) -> str:
    action_df = df.dropna(subset=["action", "cost_ms"])
    if action_df.empty:
        return ""
    stats = (
        action_df.groupby("action")["cost_ms"]
        .agg(count="count", mean="mean", max="max", p95=lambda x: x.quantile(0.95))
        .sort_values("mean", ascending=False)
        .head(15)
        .reset_index()
    )
    rows_html = "".join(
        f"<tr>"
        f"<td style='font-family:monospace;padding:.3rem .5rem'>{row['action']}</td>"
        f"<td style='text-align:right;padding:.3rem .5rem'>{int(row['count'])}</td>"
        f"<td style='text-align:right;padding:.3rem .5rem'>{row['mean']:.0f}</td>"
        f"<td style='text-align:right;padding:.3rem .5rem'>{row['p95']:.0f}</td>"
        f"<td style='text-align:right;padding:.3rem .5rem'>{row['max']:.0f}</td>"
        f"</tr>"
        for _, row in stats.iterrows()
    )
    return (
        "<h3 style='font-size:.9rem;margin:1rem 0 .5rem'>Action Performance</h3>"
        "<div style='overflow-x:auto'>"
        "<table style='width:100%;border-collapse:collapse;font-size:.85rem'>"
        "<thead><tr style='border-bottom:2px solid #dee2e6'>"
        "<th style='text-align:left;padding:.3rem .5rem'>Action</th>"
        "<th style='text-align:right;padding:.3rem .5rem'>Count</th>"
        "<th style='text-align:right;padding:.3rem .5rem'>Avg ms</th>"
        "<th style='text-align:right;padding:.3rem .5rem'>P95 ms</th>"
        "<th style='text-align:right;padding:.3rem .5rem'>Max ms</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody></table></div>"
    )


def _level_chart(df: pd.DataFrame) -> str:
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return ""
    df["minute"] = df["timestamp"].dt.floor("min")
    grp = df.groupby(["minute", "level"]).size().unstack(fill_value=0).reset_index()
    fig = go.Figure()
    for lvl, color in [("ERROR","#dc3545"),("WARN","#fd7e14"),("DEBUG","#6c757d"),("TRACE","#adb5bd")]:
        if lvl in grp.columns:
            fig.add_trace(go.Bar(x=grp["minute"], y=grp[lvl], name=lvl, marker_color=color))
    fig.update_layout(
        title="Log Level Distribution Over Time", barmode="stack",
        xaxis_title="Time", yaxis_title="Count/min",
        height=260, margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.3),
    )
    return fig_to_html(fig)
