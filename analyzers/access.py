"""
Access log analyzer.

Real entry types:
  defaultRealm:USER (sid:SID)
  "Receive request from IP(host) remote user=USER" true
  "Requset dump: METHOD /path HTTP/1.1 ..."
  "Responded to IP(host) remote user=USER" true
  "\n\tHTTP/1.1 STATUS ..." (response dump)
  "do Post got Request URI: /path"
  "Response file:/path STATUS_CODE" true
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

_RECEIVE_RE  = re.compile(r'Receive request from ([\d.:]+)\(([^)]*)\).*?remote user=([^\s"]+)')
_RESPOND_RE  = re.compile(r'Responded to ([\d.:]+)\(([^)]*)\).*?remote user=([^\s"]+)')
_METHOD_RE   = re.compile(r'(GET|POST|PUT|DELETE|OPTIONS|HEAD|PATCH)\s+(/\S*)\s+HTTP')
_STATUS_RE   = re.compile(r'HTTP/\d\.\d (\d{3})')
_FILE_RE     = re.compile(r'Response file:(/\S+?)\s+(\d{3})')
_DOPOST_RE   = re.compile(r'do Post got Request URI:\s*(\S+)')
_SID_RE      = re.compile(r'sid:([A-F0-9a-f]{16,})')
_REALM_RE    = re.compile(r'^(\w+):([^\s(]+)')


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

    # ── Stat cards ──────────────────────────────────────────────
    total     = len(df)
    requests  = int(df["is_request"].sum())
    responses = int(df["is_response"].sum())
    file_hits = int(df["is_file_response"].sum())
    unique_ips = int(df["remote_ip"].nunique()) if "remote_ip" in df.columns else 0
    unique_sids = int(df["sid"].nunique()) if "sid" in df.columns else 0

    cards = [
        stat_card("Total entries",   str(total)),
        stat_card("Requests",        str(requests)),
        stat_card("Responses",       str(responses)),
        stat_card("File responses",  str(file_hits)),
        stat_card("Unique IPs",      str(unique_ips)),
        stat_card("Sessions (SIDs)", str(unique_sids)),
    ]
    if "level" in df.columns:
        cards.append(stat_card("Errors", str(int((df["level"] == "ERROR").sum()))))
    parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    # ── Activity over time ───────────────────────────────────────
    if "timestamp" in df.columns:
        chart = _activity_chart(df)
        if chart:
            parts.append(chart)

    # ── Status code distribution ─────────────────────────────────
    status_chart = _status_chart(df)
    if status_chart:
        parts.append(status_chart)

    # ── HTTP method distribution ─────────────────────────────────
    method_chart = _method_chart(df)
    if method_chart:
        parts.append(method_chart)

    # ── Top accessed paths ───────────────────────────────────────
    path_table = _top_paths_table(df)
    if path_table:
        parts.append(path_table)

    # ── Top remote IPs ───────────────────────────────────────────
    ip_table = _top_ips_table(df)
    if ip_table:
        parts.append(ip_table)

    return section_wrap(lf.filename, lf.log_type, "\n".join(parts))


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_request"]      = False
    df["is_response"]     = False
    df["is_file_response"] = False
    df["remote_ip"]       = pd.NA
    df["remote_user"]     = pd.NA
    df["http_method"]     = pd.NA
    df["http_status"]     = pd.NA
    df["request_path"]    = pd.NA
    df["sid"]             = pd.NA
    df["realm_user"]      = pd.NA

    for idx, row in df.iterrows():
        msg = str(row.get("message", "") or "")

        # SID from every message
        m = _SID_RE.search(msg)
        if m:
            df.at[idx, "sid"] = m.group(1)

        # Realm user from first line prefix
        m = _REALM_RE.search(msg)
        if m and m.group(2) not in ("-", ""):
            df.at[idx, "realm_user"] = m.group(2)

        # Receive request
        m = _RECEIVE_RE.search(msg)
        if m:
            df.at[idx, "is_request"]  = True
            df.at[idx, "remote_ip"]   = m.group(1)
            df.at[idx, "remote_user"] = m.group(3)

        # Responded
        m = _RESPOND_RE.search(msg)
        if m:
            df.at[idx, "is_response"] = True
            df.at[idx, "remote_ip"]   = m.group(1)
            df.at[idx, "remote_user"] = m.group(3)

        # HTTP method + path (from request dump)
        m = _METHOD_RE.search(msg)
        if m:
            df.at[idx, "http_method"]  = m.group(1)
            df.at[idx, "request_path"] = m.group(2)

        # HTTP status (from response dump)
        m = _STATUS_RE.search(msg)
        if m:
            df.at[idx, "http_status"] = m.group(1)

        # Response file (static asset)
        m = _FILE_RE.search(msg)
        if m:
            df.at[idx, "is_file_response"] = True
            df.at[idx, "request_path"]     = m.group(1)
            df.at[idx, "http_status"]      = m.group(2)

        # do Post
        m = _DOPOST_RE.search(msg)
        if m:
            df.at[idx, "request_path"] = m.group(1)

    return df


def _activity_chart(df: pd.DataFrame) -> str:
    ts_df = df.dropna(subset=["timestamp"]).copy()
    if ts_df.empty:
        return ""

    ts_df["minute"] = ts_df["timestamp"].dt.floor("min")
    total_counts  = ts_df.groupby("minute").size().reset_index(name="n")
    req_counts    = ts_df[ts_df["is_request"]].groupby("minute").size().reset_index(name="n")
    file_counts   = ts_df[ts_df["is_file_response"]].groupby("minute").size().reset_index(name="n")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=total_counts["minute"], y=total_counts["n"],
        mode="lines", name="All entries",
        line=dict(color="#94a3b8"),
    ))
    if not req_counts.empty:
        fig.add_trace(go.Scatter(
            x=req_counts["minute"], y=req_counts["n"],
            mode="lines+markers", name="API requests",
            line=dict(color="#1a3a5c"),
        ))
    if not file_counts.empty:
        fig.add_trace(go.Scatter(
            x=file_counts["minute"], y=file_counts["n"],
            mode="lines", name="File responses",
            line=dict(color="#4caf50", dash="dot"),
        ))
    fig.update_layout(
        title="Access Activity Over Time",
        xaxis_title="Time", yaxis_title="Count / min",
        height=300, margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.35),
    )
    return fig_to_html(fig)


def _status_chart(df: pd.DataFrame) -> str:
    statuses = df["http_status"].dropna()
    if statuses.empty:
        return ""
    counts = statuses.value_counts().sort_index()
    colors = {
        "2": "#4caf50", "3": "#2196f3",
        "4": "#ff9800", "5": "#f44336",
    }
    bar_colors = [colors.get(str(s)[0], "#9e9e9e") for s in counts.index]
    fig = go.Figure(go.Bar(
        x=counts.index.tolist(),
        y=counts.values.tolist(),
        marker_color=bar_colors,
    ))
    fig.update_layout(
        title="HTTP Status Code Distribution",
        xaxis_title="Status", yaxis_title="Count",
        height=250, margin=dict(l=40, r=20, t=40, b=40),
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


def _top_paths_table(df: pd.DataFrame) -> str:
    paths = df["request_path"].dropna()
    if paths.empty:
        return ""
    top = paths.value_counts().head(15).reset_index()
    top.columns = ["path", "count"]
    rows_html = "".join(
        f"<tr><td style='font-family:monospace;padding:.3rem .5rem;word-break:break-all'>{row['path']}</td>"
        f"<td style='text-align:right;padding:.3rem .75rem'>{row['count']}</td></tr>"
        for _, row in top.iterrows()
    )
    return (
        "<h3 style='font-size:.9rem;margin:1rem 0 .5rem'>Top Accessed Paths</h3>"
        "<table style='border-collapse:collapse;font-size:.85rem;width:100%'>"
        "<thead><tr style='border-bottom:2px solid #dee2e6'>"
        "<th style='text-align:left;padding:.3rem .5rem'>Path</th>"
        "<th style='text-align:right;padding:.3rem .75rem'>Hits</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
    )


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
