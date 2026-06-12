"""JVM health scanner — phase-1 signals: OOM, crash markers, restarts, JVM version, heap args."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from log_parser import LogFile
from analyzers._base import apply_time_filter, stat_card


# ── Signal definitions ───────────────────────────────────────────────────────
# (key, compiled_regex, severity)
_SIGNALS: list[tuple[str, re.Pattern, str]] = [
    ("OutOfMemoryError",
     re.compile(r"java\.lang\.OutOfMemoryError", re.IGNORECASE),
     "CRITICAL"),
    ("GC Overhead Limit Exceeded",
     re.compile(r"GC overhead limit exceeded", re.IGNORECASE),
     "CRITICAL"),
    ("JVM Fatal Error",
     re.compile(r"#\s*A fatal error has been detected by the Java Runtime", re.IGNORECASE),
     "CRITICAL"),
    ("JVM Crash File Referenced",
     re.compile(r"hs_err_pid\d*\.log", re.IGNORECASE),
     "CRITICAL"),
    ("JVM Abort",
     re.compile(r"Aborting JVM|JVM is exiting abnormally|JVM terminated", re.IGNORECASE),
     "CRITICAL"),
    ("StackOverflowError",
     re.compile(r"java\.lang\.StackOverflowError", re.IGNORECASE),
     "HIGH"),
    ("Thread Deadlock",
     re.compile(r"Found one Java-level deadlock|DEADLOCK DETECTED", re.IGNORECASE),
     "HIGH"),
    ("JVM Pause",
     re.compile(r"JVM(?:\s+was)?\s+paused\s+for\s+\d+\s*ms", re.IGNORECASE),
     "WARN"),
]

_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "WARN": 2, "INFO": 3}

# Heap/GC args anywhere in raw text (header blocks include JVM options lines)
_JVM_ARG_RE = re.compile(
    r"-X(?:mx|ms|mn|ss|m|log|ss)\S+|-XX:[+-]?\w[^\s,;\"\']*",
    re.IGNORECASE,
)


def jvm_health_block(
    lf: LogFile,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> str:
    """Return an HTML block with JVM health findings, or '' if nothing notable."""
    findings = _scan_df(lf, time_from, time_to)
    jvm_args = _extract_jvm_args(lf.raw_text)

    jvm_versions = sorted({h.jvm_version for h in lf.headers if h.jvm_version})
    restart_count = len(lf.headers)

    if not findings and not jvm_args and not jvm_versions:
        return ""

    parts: list[str] = []

    # ── Stat cards ──────────────────────────────────────────────────────────
    cards: list[str] = []
    if jvm_versions:
        ver_display = jvm_versions[0]
        if len(jvm_versions) > 1:
            ver_display += f" (+{len(jvm_versions)-1} more)"
        cards.append(stat_card("JVM Version", ver_display[:70]))
    if restart_count:
        cards.append(stat_card("Server Restarts", str(restart_count)))

    oom_count   = sum(f["count"] for f in findings if "OutOfMemory"  in f["key"])
    crash_count = sum(f["count"] for f in findings if any(k in f["key"] for k in ("Fatal", "Crash", "Abort")))
    if oom_count:
        cards.append(_severity_stat_card("OutOfMemoryError", str(oom_count), "CRITICAL"))
    if crash_count:
        cards.append(_severity_stat_card("JVM Crash Signals", str(crash_count), "CRITICAL"))

    if cards:
        parts.append(f'<div class="stat-cards">{"".join(cards)}</div>')

    # ── Findings table ───────────────────────────────────────────────────────
    if findings:
        parts.append(_findings_table(findings))

    # ── JVM args ─────────────────────────────────────────────────────────────
    if jvm_args:
        parts.append(_jvm_args_block(jvm_args))

    if not parts:
        return ""

    worst = (
        min(findings, key=lambda f: _SEV_ORDER.get(f["severity"], 99))["severity"]
        if findings else "INFO"
    )

    n_signals = sum(f["count"] for f in findings)
    summary_label = _summary_label(worst, n_signals)

    body = "\n".join(parts)
    return (
        f'<details class="jvm-health-block" open>'
        f'<summary>{summary_label}</summary>'
        f'<div class="jvm-health-body">{body}</div>'
        f'</details>'
    )


# ── Internals ────────────────────────────────────────────────────────────────

def _scan_df(lf: LogFile, time_from: Optional[str], time_to: Optional[str]) -> list[dict]:
    if not lf.has_data or "message" not in lf.df.columns:
        return []
    df = apply_time_filter(lf.df.copy(), time_from, time_to)
    if df.empty:
        return []

    results: list[dict] = []
    for key, pat, severity in _SIGNALS:
        mask = df["message"].str.contains(pat, regex=True, na=False)
        matched = df[mask]
        if matched.empty:
            continue

        ts_col  = matched["timestamp"].dropna() if "timestamp" in matched.columns else pd.Series(dtype="object")
        first_ts = str(ts_col.min())[:19] if not ts_col.empty else "—"
        last_ts  = str(ts_col.max())[:19] if not ts_col.empty else "—"

        # Find first line of first match that contains the pattern
        sample_msg = matched.iloc[0]["message"]
        excerpt = ""
        for line in sample_msg.split("\n"):
            if pat.search(line):
                excerpt = line.strip()[:160]
                break
        if not excerpt:
            excerpt = sample_msg.split("\n")[0].strip()[:160]

        results.append({
            "key":      key,
            "severity": severity,
            "count":    int(mask.sum()),
            "first_ts": first_ts,
            "last_ts":  last_ts,
            "excerpt":  excerpt,
        })

    results.sort(key=lambda f: _SEV_ORDER.get(f["severity"], 99))
    return results


def _extract_jvm_args(raw_text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in _JVM_ARG_RE.finditer(raw_text):
        seen[m.group(0)] = None
    return list(seen.keys())[:40]


def _summary_label(worst: str, n_signals: int) -> str:
    _badge_bg  = {"CRITICAL": "#fee2e2", "HIGH": "#fff3e0", "WARN": "#fffbeb", "INFO": "#f1f5f9"}
    _badge_col = {"CRITICAL": "#991b1b", "HIGH": "#92400e", "WARN": "#b45309", "INFO": "#475569"}
    _badge_bdr = {"CRITICAL": "#fca5a5", "HIGH": "#fcd34d", "WARN": "#fde68a", "INFO": "#cbd5e1"}
    bg  = _badge_bg.get(worst, "#f1f5f9")
    col = _badge_col.get(worst, "#475569")
    bdr = _badge_bdr.get(worst, "#cbd5e1")
    badge = (
        f'<span style="background:{bg};color:{col};border:1px solid {bdr};'
        f'border-radius:3px;padding:1px 7px;font-size:.68rem;font-weight:700">'
        f'{worst}</span>'
    )
    signal_pill = (
        f'&nbsp;<span style="font-size:.72rem;color:#64748b">'
        f'{n_signals} signal{"s" if n_signals != 1 else ""}</span>'
    ) if n_signals else ""
    return (
        f'<span style="font-weight:600;color:#1a3a5c">JVM Health</span>'
        f'&nbsp;{badge}{signal_pill}'
    )


def _findings_table(findings: list[dict]) -> str:
    _sev_style = {
        "CRITICAL": "background:#fee2e2;color:#991b1b;border:1px solid #fca5a5",
        "HIGH":     "background:#fff3e0;color:#92400e;border:1px solid #fcd34d",
        "WARN":     "background:#fffbeb;color:#b45309;border:1px solid #fde68a",
        "INFO":     "background:#f1f5f9;color:#475569;border:1px solid #cbd5e1",
    }

    def sev_badge(sev: str) -> str:
        style = _sev_style.get(sev, _sev_style["INFO"])
        return (
            f'<span style="font-size:.68rem;font-weight:700;border-radius:3px;'
            f'padding:1px 6px;white-space:nowrap;{style}">{sev}</span>'
        )

    rows_html = ""
    for f in findings:
        rows_html += (
            "<tr>"
            f"<td style='padding:.3rem .5rem;white-space:nowrap'>{sev_badge(f['severity'])}</td>"
            f"<td style='padding:.3rem .5rem;font-weight:600;font-size:.82rem'>{_esc(f['key'])}</td>"
            f"<td style='padding:.3rem .5rem;text-align:right;font-weight:700;color:#1a3a5c'>{f['count']}</td>"
            f"<td style='padding:.3rem .5rem;font-size:.78rem;white-space:nowrap;color:#64748b'>{f['first_ts']}</td>"
            f"<td style='padding:.3rem .5rem;font-size:.78rem;white-space:nowrap;color:#64748b'>{f['last_ts']}</td>"
            f"<td style='padding:.3rem .5rem;font-family:monospace;font-size:.75rem;color:#334155;"
            f"max-width:420px;word-break:break-word'>{_esc(f['excerpt'])}</td>"
            "</tr>"
        )

    return (
        "<h3 style='font-size:.85rem;font-weight:600;margin:.75rem 0 .4rem;color:#1a3a5c'>"
        "JVM Signal Findings</h3>"
        "<div style='overflow-x:auto'>"
        "<table style='width:100%;border-collapse:collapse;font-size:.82rem'>"
        "<thead><tr style='border-bottom:2px solid #dee2e6'>"
        "<th style='text-align:left;padding:.3rem .5rem;font-size:.73rem;color:#64748b'>Severity</th>"
        "<th style='text-align:left;padding:.3rem .5rem;font-size:.73rem;color:#64748b'>Signal</th>"
        "<th style='text-align:right;padding:.3rem .5rem;font-size:.73rem;color:#64748b'>Count</th>"
        "<th style='text-align:left;padding:.3rem .5rem;font-size:.73rem;color:#64748b'>First Seen</th>"
        "<th style='text-align:left;padding:.3rem .5rem;font-size:.73rem;color:#64748b'>Last Seen</th>"
        "<th style='text-align:left;padding:.3rem .5rem;font-size:.73rem;color:#64748b'>Sample Excerpt</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )


def _jvm_args_block(args: list[str]) -> str:
    args_html = "".join(
        f'<code style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:3px;'
        f'padding:1px 6px;font-size:.75rem;margin:2px;display:inline-block">'
        f'{_esc(a)}</code>'
        for a in args
    )
    return (
        "<details style='margin-top:.75rem'>"
        "<summary style='cursor:pointer;font-size:.82rem;font-weight:600;color:#1a3a5c;"
        "list-style:none;display:block;padding:.25rem 0'>"
        "&#9654; JVM Arguments Detected</summary>"
        f"<div style='margin-top:.5rem;line-height:2.2'>{args_html}</div>"
        "</details>"
    )


def _severity_stat_card(label: str, value: str, severity: str) -> str:
    _bg  = {"CRITICAL": "#fee2e2", "HIGH": "#fff3e0", "WARN": "#fffbeb"}
    _col = {"CRITICAL": "#991b1b", "HIGH": "#92400e", "WARN": "#b45309"}
    bg  = _bg.get(severity, "#f0f4f8")
    col = _col.get(severity, "#1a3a5c")
    return (
        f'<div class="stat-card" style="background:{bg}">'
        f'<div class="label">{label}</div>'
        f'<div class="value" style="color:{col}">{value}</div>'
        f'</div>'
    )


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
