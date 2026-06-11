"""
Performance log analyzer.

Expected columns (once real format is known):
  timestamp, report_name, execution_time_ms, export_time_ms, user

Until real log samples are available this analyzer operates on the generic
DataFrame produced by log_parser._generic_line_parse and extracts any numeric
value that looks like a duration from the message text.
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

LOG_TYPES = ["performance"]

# Pattern to pull a duration value from log lines (ms, seconds, etc.)
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*ms\b", re.I)


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

    # --- extract duration_ms from message if a dedicated column isn't present ---
    if "execution_time_ms" not in df.columns:
        df["duration_ms"] = df["message"].str.extract(_DURATION_RE, expand=False).astype(float)

    duration_col = "execution_time_ms" if "execution_time_ms" in df.columns else "duration_ms"
    has_duration = duration_col in df.columns and df[duration_col].notna().any()

    parts: list[str] = []

    # Stat cards
    cards_html = _build_stat_cards(df, duration_col, has_duration)
    parts.append(f'<div class="stat-cards">{cards_html}</div>')

    # Duration-over-time chart
    if has_duration and "timestamp" in df.columns:
        ts_df = df.dropna(subset=["timestamp", duration_col]).sort_values("timestamp")
        if not ts_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ts_df["timestamp"],
                y=ts_df[duration_col],
                mode="lines+markers",
                name="Duration (ms)",
                line=dict(color="#1a3a5c"),
                marker=dict(size=4),
            ))
            fig.update_layout(
                title="Report Execution Duration Over Time",
                xaxis_title="Time",
                yaxis_title="Duration (ms)",
                height=350,
                margin=dict(l=40, r=20, t=40, b=40),
            )
            parts.append(fig_to_html(fig))

    # Error/warn rate over time (bucketed by minute)
    if "level" in df.columns and "timestamp" in df.columns:
        error_chart = _error_rate_chart(df)
        if error_chart:
            parts.append(error_chart)

    # Placeholder note
    parts.append(
        '<p class="note" style="font-size:.8rem;color:#888;margin-top:.5rem;">'
        'Tip: share a real performance.log sample to unlock dedicated column parsing '
        '(report name, user, export time).'
        '</p>'
    )

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _build_stat_cards(df: pd.DataFrame, duration_col: str, has_duration: bool) -> str:
    cards = []
    cards.append(stat_card("Total rows", str(len(df))))

    if has_duration:
        d = df[duration_col].dropna()
        cards.append(stat_card("Avg duration", f"{d.mean():.0f} ms"))
        cards.append(stat_card("Max duration", f"{d.max():.0f} ms"))
        cards.append(stat_card("P95 duration", f"{d.quantile(0.95):.0f} ms"))

    if "level" in df.columns:
        errors = (df["level"] == "ERROR").sum()
        cards.append(stat_card("Errors", str(errors)))

    return "".join(cards)


def _error_rate_chart(df: pd.DataFrame) -> str:
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return ""

    df = df.copy()
    df["minute"] = df["timestamp"].dt.floor("min")
    counts = df.groupby(["minute", "level"]).size().unstack(fill_value=0).reset_index()

    fig = go.Figure()
    for lvl, color in [("ERROR", "#dc3545"), ("WARN", "#fd7e14"), ("INFO", "#0d6efd")]:
        if lvl in counts.columns:
            fig.add_trace(go.Bar(x=counts["minute"], y=counts[lvl], name=lvl,
                                 marker_color=color))

    fig.update_layout(
        title="Log Level Distribution Over Time",
        barmode="stack",
        xaxis_title="Time",
        yaxis_title="Count",
        height=300,
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.25),
    )
    return fig_to_html(fig)
