"""
Generic fallback analyzer for unrecognised log types.
Shows activity volume and level distribution using whatever the parser extracted.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from log_parser import LogFile
from analyzers._base import (
    apply_time_filter, fig_to_html, stat_card, section_wrap, no_data_section
)

LOG_TYPES = ["unknown"]


async def analyze(
    lf: LogFile,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> str:
    if not lf.has_data:
        return no_data_section(lf.filename, lf.log_type, "Could not parse any rows from this file.")

    df = apply_time_filter(lf.df.copy(), time_from, time_to)
    if df.empty:
        return no_data_section(lf.filename, lf.log_type, "No data in the selected time range.")

    parts: list[str] = []
    cards = [stat_card("Total entries", str(len(df)))]
    if "level" in df.columns:
        cards.append(stat_card("Errors",   str((df["level"] == "ERROR").sum())))
        cards.append(stat_card("Warnings", str((df["level"] == "WARN").sum())))
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    if "timestamp" in df.columns:
        df_ts = df.dropna(subset=["timestamp"]).copy()
        if not df_ts.empty:
            df_ts["minute"] = df_ts["timestamp"].dt.floor("min")

            if "level" in df_ts.columns:
                grp = df_ts.groupby(["minute", "level"]).size().unstack(fill_value=0).reset_index()
                fig = go.Figure()
                for lvl, color in [("ERROR","#dc3545"),("WARN","#fd7e14"),
                                   ("INFO","#0d6efd"),("DEBUG","#6c757d"),("TRACE","#adb5bd")]:
                    if lvl in grp.columns:
                        fig.add_trace(go.Bar(x=grp["minute"], y=grp[lvl],
                                             name=lvl, marker_color=color))
                fig.update_layout(
                    title="Log Activity Over Time", barmode="stack",
                    xaxis_title="Time", yaxis_title="Count/min",
                    height=300, margin=dict(l=40, r=20, t=40, b=40),
                    legend=dict(orientation="h", y=-0.3),
                )
            else:
                counts = df_ts.groupby("minute").size().reset_index(name="events")
                fig = go.Figure(go.Scatter(
                    x=counts["minute"], y=counts["events"],
                    mode="lines", fill="tozeroy",
                    line=dict(color="#6c757d"),
                ))
                fig.update_layout(
                    title="Log Activity Over Time",
                    xaxis_title="Time", yaxis_title="Events/min",
                    height=280, margin=dict(l=40, r=20, t=40, b=40),
                )
            parts.append(fig_to_html(fig))

    parts.append(
        '<p style="font-size:.8rem;color:#888;margin-top:.5rem;">'
        'Log type not recognised from filename. Rename your file to include one of: '
        'performance, access, error, engine, dhtml, page, manage, event, debug, dump '
        '— or share a sample so a dedicated parser can be added.'
        '</p>'
    )

    return section_wrap(lf.filename, f"{lf.log_type} (unrecognised)", "\n".join(parts))
