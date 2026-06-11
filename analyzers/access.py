"""
Access log analyzer.

Access log entries contain HTTP request/response traces:
  "Receive request from <ip>(<hostname>) remote user=<user>"
  "Responded to <ip>..."
  HTTP method + path lines

Extracts:
  - Request volume over time
  - HTTP method distribution
  - Remote IP / user distribution
  - Response activity timeline
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

LOG_TYPES = ["access"]

_RECEIVE_RE = re.compile(
    r"Receive request from ([\d.]+)\(([^)]*)\).*?remote user=(\S+)"
)
_RESPOND_RE = re.compile(
    r"Responded to ([\d.]+)\(([^)]*)\).*?remote user=(\S+)"
)
_METHOD_RE  = re.compile(r"^\s*(GET|POST|PUT|DELETE|OPTIONS|HEAD|PATCH)\s+(\S+)")
_SID_RE     = re.compile(r"sid:([A-F0-9]+)")


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
    requests  = df["is_request"].sum()  if "is_request"  in df.columns else 0
    responses = df["is_response"].sum() if "is_response" in df.columns else 0
    unique_ips = df["remote_ip"].nunique() if "remote_ip" in df.columns else 0
    cards = [
        stat_card("Total entries", str(total)),
        stat_card("Requests",  str(int(requests))),
        stat_card("Responses", str(int(responses))),
        stat_card("Unique IPs", str(int(unique_ips))),
    ]
    if "level" in df.columns:
        cards.append(stat_card("Errors", str((df["level"] == "ERROR").sum())))
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    # ── Request volume over time ─────────────────────────────
    if "timestamp" in df.columns and requests > 0:
        chart = _volume_chart(df)
        if chart:
            parts.append(chart)

    # ── HTTP method distribution ─────────────────────────────
    if "http_method" in df.columns:
        method_chart = _method_chart(df)
        if method_chart:
            parts.append(method_chart)

    # ── Top remote IPs ───────────────────────────────────────
    if "remote_ip" in df.columns:
        parts.append(_top_ips_table(df))

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_request"]  = False
    df["is_response"] = False
    df["remote_ip"]   = pd.NA
    df["remote_host"] = pd.NA
    df["remote_user"] = pd.NA
    df["http_method"] = pd.NA

    for idx, row in df.iterrows():
        msg = row.get("message", "") or ""
        m = _RECEIVE_RE.search(msg)
        if m:
            df.at[idx, "is_request"]  = True
            df.at[idx, "remote_ip"]   = m.group(1)
            df.at[idx, "remote_host"] = m.group(2)
            df.at[idx, "remote_user"] = m.group(3)
            continue
        m = _RESPOND_RE.search(msg)
        if m:
            df.at[idx, "is_response"] = True
            df.at[idx, "remote_ip"]   = m.group(1)
            df.at[idx, "remote_host"] = m.group(2)
            df.at[idx, "remote_user"] = m.group(3)
            continue
        m = _METHOD_RE.search(msg)
        if m:
            df.at[idx, "http_method"] = m.group(1)

    return df


def _volume_chart(df: pd.DataFrame) -> str:
    df_req = df[df["is_request"]].dropna(subset=["timestamp"]).copy()
    df_res = df[df["is_response"]].dropna(subset=["timestamp"]).copy()
    if df_req.empty and df_res.empty:
        return ""

    fig = go.Figure()
    for sub_df, name, color in [
        (df_req, "Requests",  "#1a3a5c"),
        (df_res, "Responses", "#4caf50"),
    ]:
        if not sub_df.empty:
            sub_df = sub_df.copy()
            sub_df["minute"] = sub_df["timestamp"].dt.floor("min")
            counts = sub_df.groupby("minute").size().reset_index(name="n")
            fig.add_trace(go.Scatter(
                x=counts["minute"], y=counts["n"],
                mode="lines", name=name,
                line=dict(color=color),
            ))
    fig.update_layout(
        title="Request / Response Volume Over Time",
        xaxis_title="Time", yaxis_title="Count/min",
        height=300, margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.3),
    )
    return fig_to_html(fig)


def _method_chart(df: pd.DataFrame) -> str:
    methods = df["http_method"].dropna()
    if methods.empty:
        return ""
    counts = methods.value_counts()
    fig = go.Figure(go.Bar(
        x=counts.index.tolist(),
        y=counts.values.tolist(),
        marker_color="#1a3a5c",
    ))
    fig.update_layout(
        title="HTTP Method Distribution",
        xaxis_title="Method", yaxis_title="Count",
        height=250, margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig_to_html(fig)


def _top_ips_table(df: pd.DataFrame) -> str:
    ips = df["remote_ip"].dropna()
    if ips.empty:
        return ""
    top = ips.value_counts().head(10).reset_index()
    top.columns = ["ip", "count"]
    rows_html = "".join(
        f"<tr><td style='font-family:monospace;padding:.3rem .5rem'>{row['ip']}</td>"
        f"<td style='text-align:right;padding:.3rem .75rem'>{row['count']}</td></tr>"
        for _, row in top.iterrows()
    )
    return (
        "<h3 style='font-size:.9rem;margin:1rem 0 .5rem'>Top Remote IPs</h3>"
        "<table style='border-collapse:collapse;font-size:.85rem'>"
        "<thead><tr style='border-bottom:2px solid #dee2e6'>"
        "<th style='text-align:left;padding:.3rem .5rem'>IP</th>"
        "<th style='text-align:right;padding:.3rem .75rem'>Requests</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
    )
