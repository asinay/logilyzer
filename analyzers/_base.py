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
