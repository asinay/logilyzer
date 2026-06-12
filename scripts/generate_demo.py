"""
Generate realistic fake log files and produce a demo report HTML.
Output: demo/sample_report.html
"""
import asyncio
import random
import pathlib
import sys
import os

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from datetime import datetime, timedelta
from log_parser import parse_log_file
from analyzers import get_analyzer
from analyzers._base import apply_time_filter, raw_log_block, server_info_block, _raw_table_counter

rng = random.Random(42)

BASE = datetime(2026, 4, 3, 8, 0, 0)


def ts(dt):
    return dt.strftime("%d %m %Y %H:%M:%S") + f",{rng.randint(0, 999):03d}"


def entry(msg, thread, level, dt):
    return f"{msg} [{thread}][{level}][{ts(dt)} +0200]\n"


def header_block(dt):
    sep = "=" * 16 + dt.strftime("%a %b %d %H:%M:%S CET %Y") + "=" * 16
    return (
        f"{sep}\n"
        "The Java VM version : 17.0.14\n"
        "Version: Logi Report Server V25.1 Service Pack 2\n"
        "Version Number: 25.1.2.0\n"
        "Internal Version Label: B202601151800\n"
        "\n"
        f" [main][ERROR][{ts(dt)} +0200]\n"
    )


# ---------------------------------------------------------------------------
# Engine.log
# ---------------------------------------------------------------------------
def make_engine():
    lines = [header_block(BASE)]
    t = BASE + timedelta(seconds=5)
    reports = [
        ("Q1 Sales Dashboard",        1200, 4500),
        ("Customer Churn Analysis",    800, 12000),
        ("Inventory Status",           600,  3200),
        ("Revenue by Region",         2100,  8700),
        ("HR Headcount Summary",       300,  1800),
        ("Product Performance",        950,  6400),
        ("Finance P&L",               1500, 22000),
        ("Ops KPI Dashboard",          400,  2900),
    ]
    threads = [f"Thread-{i}" for i in range(20, 55)]
    for _ in range(300):
        rep, base_e, max_e = rng.choice(reports)
        elapsed = rng.randint(base_e, max_e)
        thread = rng.choice(threads)
        lvl = "WARN" if elapsed > 15000 else "INFO"
        user = f"analyst{rng.randint(1,8)}@acme.com"
        lines.append(entry(f'Running report "{rep}" user={user}', thread, lvl, t))
        t += timedelta(milliseconds=rng.randint(200, 2000))
        lines.append(entry(f"ELAPSED:{elapsed} report=\"{rep}\" method=POST", thread, lvl, t))
        t += timedelta(milliseconds=rng.randint(100, 500))
        if rng.random() < 0.10:
            lines.append(entry(f"Elapsed(MS):{rng.randint(500, 3000)} waiting for connection pool", thread, "WARN", t))
            t += timedelta(milliseconds=rng.randint(50, 200))

    # mid-day restart
    t2 = BASE + timedelta(hours=4, minutes=17)
    lines.append(header_block(t2))
    t = t2 + timedelta(seconds=3)
    for _ in range(140):
        rep, base_e, max_e = rng.choice(reports)
        elapsed = rng.randint(base_e, max_e)
        thread = rng.choice(threads)
        lvl = "ERROR" if elapsed > 20000 else "INFO"
        lines.append(entry(f'Running report "{rep}" user=analyst{rng.randint(1,8)}@acme.com', thread, lvl, t))
        t += timedelta(milliseconds=rng.randint(300, 3000))
        lines.append(entry(f"ELAPSED:{elapsed} report=\"{rep}\" method=GET", thread, lvl, t))
        t += timedelta(milliseconds=rng.randint(100, 400))

    return "".join(lines)


# ---------------------------------------------------------------------------
# Error.log
# ---------------------------------------------------------------------------
def make_error():
    lines = [header_block(BASE)]
    t = BASE + timedelta(seconds=12)
    threads = [f"Thread-{i}" for i in range(20, 55)]
    errors = [
        ("java.sql.SQLException",
         "Connection timed out after 30000ms waiting for pool"),
        ("com.jinfonet.report.engine.EngineException",
         "Report compilation failed: syntax error near token at line 42"),
        ("java.lang.OutOfMemoryError",
         "Java heap space exhausted during PDF export"),
        ("com.jinfonet.security.AuthException",
         "Session expired: sid:3FA2B1C expired after 1800s idle"),
        ("java.net.SocketTimeoutException",
         "Read timed out connecting to datasource PROD_DB"),
        ("com.jinfonet.report.ParameterException",
         "Required parameter StartDate is missing from request"),
    ]
    for _ in range(95):
        exc, msg = rng.choice(errors)
        thread = rng.choice(threads)
        lvl = rng.choice(["ERROR", "ERROR", "ERROR", "WARN"])
        lines.append(entry(f"{exc}: {msg}", thread, lvl, t))
        t += timedelta(seconds=rng.randint(15, 180))
        if rng.random() < 0.4:
            lines.append(entry(
                "  at com.jinfonet.report.engine.ReportRunner.run(ReportRunner.java:247)\n"
                "  at com.jinfonet.server.RequestHandler.process(RequestHandler.java:88)",
                thread, lvl, t
            ))
            t += timedelta(milliseconds=rng.randint(10, 50))
    return "".join(lines)


# ---------------------------------------------------------------------------
# Access.log
# ---------------------------------------------------------------------------
def make_access():
    lines = [header_block(BASE)]
    t = BASE + timedelta(seconds=2)
    threads = [f"Thread-{i}" for i in range(20, 55)]
    ips = ["10.0.1.45", "10.0.1.67", "192.168.5.102", "10.0.1.89", "172.16.3.14"]
    hosts = ["ws01.acme.local", "ws02.acme.local", "app01.acme.local",
             "citrix01.acme.local", "vpn-gw.acme.local"]
    paths = [
        "/jrserver/api/v1.2/report/run",
        "/jrserver/api/v1.2/report/parameterInfos",
        "/jrserver/api/v1.2/report/export",
        "/jrserver/dashboard/view",
        "/jrserver/api/v1.2/catalog/list",
    ]
    users = ["jsmith", "alee", "mbrown", "tjones", "null"]
    sids = [f"{rng.randint(0, 0xFFFFFFFF):08X}{rng.randint(0, 0xFFFFFFFF):08X}" for _ in range(8)]
    pairs = list(zip(ips, hosts))
    for _ in range(180):
        ip, host = rng.choice(pairs)
        user = rng.choice(users)
        sid = rng.choice(sids)
        thread = rng.choice(threads)
        method = rng.choice(["GET", "GET", "POST", "POST", "OPTIONS"])
        path = rng.choice(paths)
        status = rng.choice(["200", "200", "200", "401", "302"])
        lines.append(entry(
            f'defaultRealm:{user} (sid:{sid})\n'
            f'"Receive request from {ip}({host}) remote user={user}" true',
            thread, "INFO", t
        ))
        t += timedelta(milliseconds=rng.randint(5, 30))
        lines.append(entry(
            f'defaultRealm:{user} (sid:{sid})\n'
            f' "Requset dump:\n\t{method} {path} HTTP/1.1\n\tHost:{host}:8888\n\tConnection:keep-alive" true',
            thread, "DEBUG", t
        ))
        t += timedelta(milliseconds=rng.randint(80, 800))
        lines.append(entry(
            f'defaultRealm:{user} (sid:{sid})\n'
            f'"Responded to {ip}({host}) remote user={user}" true',
            thread, "INFO", t
        ))
        t += timedelta(milliseconds=rng.randint(5, 20))
        lines.append(entry(
            f'defaultRealm:{user} (sid:{sid})\n'
            f' "\n\tHTTP/1.1 {status} OK\n\tDate: Fri, 03 Apr 2026 08:00:00 GMT\n\tContent-Type: application/json" true',
            thread, "DEBUG", t
        ))
        t += timedelta(milliseconds=rng.randint(100, 1200))
    return "".join(lines)


# ---------------------------------------------------------------------------
# Dump.log
# ---------------------------------------------------------------------------
def make_dump():
    lines = [header_block(BASE)]
    t = BASE + timedelta(seconds=8)
    for _ in range(220):
        od_run = rng.randint(0, 6)
        od_que = rng.randint(0, 14)
        od_wait = rng.randint(0, 8)
        sc_run = rng.randint(0, 3)
        sc_que = rng.randint(0, 7)
        sc_wait = rng.randint(0, 4)
        lines.append(entry(
            f"TaskManager status dump:\n"
            f"OnDemand:Running={od_run},Queuing={od_que},Waiting={od_wait}\n"
            f"Schedule:Running={sc_run},Queuing={sc_que},Waiting={sc_wait}",
            "TaskDumpThread", "INFO", t
        ))
        t += timedelta(seconds=rng.randint(10, 30))
    return "".join(lines)


# ---------------------------------------------------------------------------
# DHTML.log
# ---------------------------------------------------------------------------
def make_dhtml():
    lines = [header_block(BASE)]
    t = BASE + timedelta(seconds=4)
    threads = [f"Thread-{i}" for i in range(20, 55)]
    actions = [
        ("ViewDashboard",   800,  4500),
        ("RunReport",      1200, 18000),
        ("ExportToPDF",    2000, 25000),
        ("LoadParameters",  200,  1500),
        ("RefreshChart",    300,  2800),
        ("SearchCatalog",   150,   900),
        ("SaveBookmark",    100,   600),
        ("DrillDown",       400,  3200),
    ]
    for _ in range(240):
        action, base_c, max_c = rng.choice(actions)
        cost = rng.randint(base_c, max_c)
        thread = rng.choice(threads)
        lvl = "WARN" if cost > 15000 else "INFO"
        session = f"sess{rng.randint(1000, 9999)}"
        lines.append(entry(f"T-S/C-A-0-{action} {session} cost={cost}", thread, lvl, t))
        t += timedelta(milliseconds=rng.randint(200, 3000))
    return "".join(lines)


# ---------------------------------------------------------------------------
# Build report
# ---------------------------------------------------------------------------
async def build_report():
    _raw_table_counter[0] = 0

    log_sources = [
        ("Engine.log",  "engine",  make_engine()),
        ("Error.log",   "error",   make_error()),
        ("Access.log",  "access",  make_access()),
        ("Dump.log",    "dump",    make_dump()),
        ("DHTML.log",   "dhtml",   make_dhtml()),
    ]

    log_files = [parse_log_file(name, ltype, text) for name, ltype, text in log_sources]

    for lf in log_files:
        print(f"  {lf.filename}: {lf.row_count} rows, {len(lf.headers)} header block(s)")

    sections_html = []
    for lf in log_files:
        analyzer = get_analyzer(lf.log_type)
        if analyzer is None:
            sections_html.append(f'<div class="section"><h2>{lf.filename}</h2><p>No analyzer.</p></div>')
            continue
        section = await analyzer.analyze(lf)
        extras = ""
        si = server_info_block(lf.headers)
        if si:
            extras += "\n" + si
        raw = raw_log_block(lf.df, max_rows=500)
        if raw:
            extras += "\n" + raw
        if extras:
            idx = section.rfind("</div>")
            section = (section[:idx] if idx >= 0 else section) + extras + "\n</div>"
        sections_html.append(section)

    from app import _build_report
    html = _build_report(log_files, sections_html, None, None)

    out = pathlib.Path(__file__).parent.parent / "demo" / "sample_report.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"\nWrote {out} ({len(html)//1024} KB)")


if __name__ == "__main__":
    asyncio.run(build_report())
