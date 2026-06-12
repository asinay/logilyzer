import re
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from log_parser import detect_log_type, parse_log_file, LogFile
from analyzers import get_analyzer
from analyzers._base import apply_time_filter, raw_log_block, server_info_block

app = FastAPI(title="LogiLyzer")
app.mount("/static", StaticFiles(directory="static"), name="static")

OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(exist_ok=True)

# In-memory session store: session_id -> list[LogFile]
sessions: dict[str, list[LogFile]] = {}


@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path("static") / "index.html").read_text(encoding="utf-8")


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    session_id = str(uuid.uuid4())
    log_files: list[LogFile] = []

    for upload in files:
        raw = await upload.read()
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("latin-1", errors="replace")

        log_type = detect_log_type(upload.filename or "", text)
        lf = parse_log_file(upload.filename or "unknown", log_type, text)
        log_files.append(lf)

    sessions[session_id] = log_files

    return {
        "session_id": session_id,
        "files": [
            {
                "filename": lf.filename,
                "log_type": lf.log_type,
                "row_count": lf.row_count,
                "time_min": lf.time_min,
                "time_max": lf.time_max,
                "has_data": lf.has_data,
            }
            for lf in log_files
        ],
    }


@app.post("/export")
async def export_report(
    session_id: str = Form(...),
    selected_files: list[str] = Form(...),
    time_from: Optional[str] = Form(None),
    time_to: Optional[str] = Form(None),
):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    log_files = sessions[session_id]
    selected = [lf for lf in log_files if lf.filename in selected_files]

    if not selected:
        raise HTTPException(status_code=400, detail="No files selected")

    # Run all analyzers concurrently
    tasks = [
        _run_analyzer(lf, time_from, time_to)
        for lf in selected
    ]
    sections_html = await asyncio.gather(*tasks)

    output_html = _build_report(selected, sections_html, time_from, time_to)
    out_path = OUTPUTS_DIR / f"report_{session_id[:8]}.html"
    out_path.write_text(output_html, encoding="utf-8")

    return FileResponse(
        path=str(out_path),
        media_type="text/html",
        filename=out_path.name,
    )


async def _run_analyzer(lf: LogFile, time_from: Optional[str], time_to: Optional[str]) -> str:
    analyzer = get_analyzer(lf.log_type)
    if analyzer is None:
        return _unsupported_section(lf)
    try:
        section = await analyzer.analyze(lf, time_from=time_from, time_to=time_to)
        # Build extras to inject before closing </div>
        extras = ""
        si = server_info_block(lf.headers)
        if si:
            extras += "\n" + si
        filtered_df = apply_time_filter(lf.df, time_from, time_to) if lf.has_data else lf.df
        raw = raw_log_block(filtered_df)
        if raw:
            extras += "\n" + raw
        if extras:
            idx = section.rfind("</div>")
            return (section[:idx] if idx >= 0 else section) + extras + "\n</div>"
        return section
    except Exception as exc:
        return f'<div class="section error"><h2>{lf.filename}</h2><p>Analysis failed: {exc}</p></div>'


def _unsupported_section(lf: LogFile) -> str:
    return (
        f'<div class="section unsupported">'
        f'<h2>{lf.filename} <span class="badge">{lf.log_type}</span></h2>'
        f'<p>No analyzer available for this log type yet. '
        f'Raw row count: {lf.row_count}</p>'
        f'</div>'
    )


def _section_id(filename: str) -> str:
    return "sec-" + "".join(c if c.isalnum() else "-" for c in filename.lower()).strip("-")


def _build_report(
    log_files: list[LogFile],
    sections_html: list[str],
    time_from: Optional[str],
    time_to: Optional[str],
) -> str:
    time_note = ""
    if time_from or time_to:
        time_note = (
            f'<div class="time-filter">'
            f'&#128336; Time filter: <strong>{time_from or "—"}</strong> → <strong>{time_to or "—"}</strong>'
            f'</div>'
        )

    # Build sidebar nav items — version pill per file from first versioned header
    def _file_version(lf: LogFile) -> str:
        for h in lf.headers:
            if h.server_version:
                # Shorten "Logi Report Server V25.1 Service Pack 5" → "V25.1 SP5"
                v = h.server_version
                v = re.sub(r"Logi Report Server\s*", "", v, flags=re.IGNORECASE).strip()
                v = re.sub(r"Service Pack\s*(\d+)", r"SP\1", v, flags=re.IGNORECASE)
                return v
        return ""

    nav_items = ""
    for lf in log_files:
        sid = _section_id(lf.filename)
        ver = _file_version(lf)
        ver_pill = f'<span class="nav-version">{ver}</span>' if ver else ""
        nav_items += (
            f'<a class="nav-item" href="#{sid}" onclick="activate(this)">'
            f'<span class="nav-dot"></span>'
            f'<span class="nav-label">{lf.filename}</span>'
            f'{ver_pill}'
            f'<span class="nav-badge">{lf.log_type}</span>'
            f'</a>\n'
        )

    sections = "\n".join(sections_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LogiLyzer</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: system-ui, sans-serif;
    background: #f0f4f8;
    color: #1a1a2e;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }}

  /* ── Header ── */
  .report-header {{
    background: linear-gradient(135deg, #0d1b2e 0%, #1a3a5c 60%, #1e4d7b 100%);
    color: #fff;
    padding: .75rem 1.25rem;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,.2);
    position: relative;
    overflow: hidden;
  }}
  .report-header::before {{
    content: "";
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px);
    background-size: 24px 24px;
    pointer-events: none;
  }}
  .rh-logo {{
    width: 30px; height: 30px;
    flex-shrink: 0;
    filter: drop-shadow(0 1px 4px rgba(0,180,216,.4));
  }}
  .rh-brand {{ line-height: 1.2; }}
  .rh-name {{
    font-size: 1.05rem;
    font-weight: 800;
    letter-spacing: -.02em;
    display: flex;
    align-items: baseline;
  }}
  .rh-name .logi  {{ color: #fff; }}
  .rh-name .lyzer {{ color: #38bdf8; font-weight: 400; }}
  .rh-meta {{
    font-size: .72rem;
    color: rgba(255,255,255,.5);
    margin-left: .75rem;
  }}

  /* ── Layout ── */
  .layout {{
    display: flex;
    flex: 1;
    overflow: hidden;
  }}

  /* ── Sidebar ── */
  .sidebar {{
    width: 220px;
    flex-shrink: 0;
    background: #fff;
    border-right: 1px solid #dde3ea;
    overflow-y: auto;
    padding: .75rem 0;
  }}
  .sidebar-title {{
    font-size: .65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: #94a3b8;
    padding: .4rem 1rem .6rem;
  }}
  .nav-item {{
    display: flex;
    align-items: center;
    gap: .5rem;
    padding: .45rem 1rem;
    font-size: .8rem;
    color: #334155;
    text-decoration: none;
    cursor: pointer;
    transition: background .1s;
    border-right: 3px solid transparent;
  }}
  .nav-item:hover {{ background: #f1f5f9; color: #1a3a5c; }}
  .nav-item.active {{
    background: #e8f0f8;
    color: #1a3a5c;
    font-weight: 600;
    border-right-color: #1a3a5c;
  }}
  .nav-dot {{
    width: 6px; height: 6px;
    background: #1a3a5c;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .nav-label {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .nav-badge {{
    font-size: .65rem;
    background: #e8eef4;
    color: #1a3a5c;
    border-radius: 3px;
    padding: 1px 5px;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .nav-version {{
    font-size: .62rem;
    background: #d1fae5;
    color: #065f46;
    border-radius: 3px;
    padding: 1px 5px;
    white-space: nowrap;
    flex-shrink: 0;
    font-weight: 600;
  }}

  /* ── Main content ── */
  .main {{
    flex: 1;
    overflow-y: auto;
    padding: 0 0 2rem;
  }}
  .time-filter {{
    background: #fff3cd;
    border-left: 4px solid #ffc107;
    padding: .5rem 1.25rem;
    font-size: .82rem;
    margin: 1rem 1.5rem 0;
    border-radius: 0 4px 4px 0;
  }}
  .section {{
    background: #fff;
    margin: 1rem 1.5rem;
    border-radius: 6px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
    padding: 1.25rem 1.5rem;
    scroll-margin-top: 1rem;
  }}
  .section h2 {{
    margin-top: 0;
    font-size: 1rem;
    border-bottom: 2px solid #1a3a5c;
    padding-bottom: .45rem;
    margin-bottom: 1rem;
  }}
  .section.error h2   {{ border-color: #dc3545; }}
  .section.unsupported {{ opacity: .7; }}
  .badge {{
    background: #e8eef4; color: #1a3a5c;
    border-radius: 3px; padding: 2px 6px;
    font-size: .72rem; font-weight: normal;
  }}
  .stat-cards {{ display: flex; flex-wrap: wrap; gap: .65rem; margin-bottom: 1rem; }}
  .stat-card  {{
    background: #f0f4f8; border-radius: 4px;
    padding: .55rem .9rem; min-width: 120px;
  }}
  .stat-card .label {{ font-size: .72rem; color: #64748b; }}
  .stat-card .value {{ font-size: 1.15rem; font-weight: 600; color: #1a3a5c; }}
  .no-data {{ color: #94a3b8; font-size: .875rem; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: .3rem .5rem; }}
  thead tr {{ border-bottom: 2px solid #dee2e6; }}

  /* ── Server info block inside sections ── */
  .server-info-block {{
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    margin-bottom: 1rem;
    overflow: hidden;
  }}
  .server-info-block summary {{
    cursor: pointer;
    padding: .45rem .9rem;
    font-size: .82rem;
    font-weight: 600;
    color: #1a3a5c;
    background: #f6f8fb;
    user-select: none;
    list-style: none;
    display: flex;
    align-items: center;
    gap: .5rem;
  }}
  .server-info-block summary::-webkit-details-marker {{ display: none; }}
  .server-info-block summary::before {{
    content: "▶";
    font-size: .6rem;
    transition: transform .2s;
  }}
  .server-info-block[open] summary::before {{ transform: rotate(90deg); }}
  .si-title {{ flex: 1; }}
  .si-pill {{
    font-size: .68rem;
    font-weight: normal;
    background: #e8eef4;
    color: #1a3a5c;
    border-radius: 3px;
    padding: 1px 6px;
  }}
  .si-body {{
    padding: .5rem .75rem;
    overflow-x: auto;
  }}

  /* ── Sidebar filter controls ── */
  .sidebar-filter-block {{
    padding: .6rem .75rem;
    border-bottom: 1px solid #dde3ea;
    margin-bottom: .4rem;
  }}
  .sidebar-filter-block label {{
    font-size: .65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .07em;
    color: #94a3b8;
    display: block;
    margin-bottom: .35rem;
  }}
  #global-search {{
    width: 100%;
    padding: .35rem .55rem;
    border: 1px solid #ccd3dc;
    border-radius: 4px;
    font-size: .8rem;
    outline: none;
  }}
  #global-search:focus {{ border-color: #1a3a5c; }}
  .level-toggles {{
    display: flex;
    flex-wrap: wrap;
    gap: .3rem;
    margin-top: .5rem;
  }}
  .lvl-btn {{
    font-size: .68rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 3px;
    border: 1px solid transparent;
    cursor: pointer;
    opacity: .4;
    transition: opacity .15s;
  }}
  .lvl-btn.on {{ opacity: 1; }}
  .lvl-btn[data-lvl="ERROR"] {{ background:#fee2e2; color:#991b1b; border-color:#fca5a5; }}
  .lvl-btn[data-lvl="WARN"]  {{ background:#fff3e0; color:#b45309; border-color:#fcd34d; }}
  .lvl-btn[data-lvl="INFO"]  {{ background:#dbeafe; color:#1e40af; border-color:#93c5fd; }}
  .lvl-btn[data-lvl="DEBUG"] {{ background:#f1f5f9; color:#475569; border-color:#cbd5e1; }}
  .lvl-btn[data-lvl="TRACE"] {{ background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }}

  /* ── Raw log block ── */
  .raw-log {{
    margin-top: 1.25rem;
    border: 1px solid #dde3ea;
    border-radius: 5px;
    overflow: hidden;
  }}
  .raw-log summary {{
    cursor: pointer;
    padding: .5rem .9rem;
    font-size: .82rem;
    font-weight: 600;
    color: #1a3a5c;
    background: #f6f8fb;
    user-select: none;
    list-style: none;
    display: flex;
    align-items: center;
    gap: .5rem;
  }}
  .raw-log summary::-webkit-details-marker {{ display: none; }}
  .raw-log summary::before {{
    content: "▶";
    font-size: .65rem;
    transition: transform .2s;
  }}
  .raw-log[open] summary::before {{ transform: rotate(90deg); }}
  .raw-count {{
    background: #e8eef4; color: #1a3a5c;
    border-radius: 3px; padding: 1px 6px;
    font-size: .72rem; font-weight: normal;
  }}
  .raw-toolbar {{
    display: flex;
    align-items: center;
    gap: .5rem;
    padding: .5rem .75rem;
    background: #f6f8fb;
    border-bottom: 1px solid #dde3ea;
    flex-wrap: wrap;
  }}
  .raw-thread-select {{
    padding: .25rem .45rem;
    border: 1px solid #ccd3dc;
    border-radius: 4px;
    font-size: .78rem;
    outline: none;
  }}
  .raw-search {{
    flex: 1;
    min-width: 120px;
    padding: .25rem .5rem;
    border: 1px solid #ccd3dc;
    border-radius: 4px;
    font-size: .78rem;
    outline: none;
  }}
  .raw-search:focus {{ border-color: #1a3a5c; }}
  .raw-match-count {{
    font-size: .72rem;
    color: #64748b;
    white-space: nowrap;
  }}
  .raw-table thead th {{
    cursor: pointer;
    user-select: none;
  }}
  .raw-table thead th:hover {{ background: #e2eaf4; }}
  .sort-icon {{ margin-left: .3rem; font-size: .65rem; opacity: .45; }}
  .sort-asc  .sort-icon {{ opacity: 1; }}
  .sort-desc .sort-icon {{ opacity: 1; }}
  .raw-note {{ font-size:.75rem; color:#888; padding:.3rem .75rem; }}
  .raw-scroll {{ overflow-x:auto; max-height:420px; overflow-y:auto; }}
  .raw-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: .78rem;
    font-family: monospace;
  }}
  .raw-table thead th {{
    position: sticky; top: 0;
    background: #f0f4f8;
    text-align: left;
    padding: .3rem .6rem;
    border-bottom: 1px solid #dde3ea;
    font-family: system-ui, sans-serif;
    font-size: .75rem; color: #475569; white-space: nowrap;
  }}
  .raw-table tbody tr:nth-child(even) {{ background: #f9fafb; }}
  .raw-table tbody tr:hover {{ background: #e8f0f8; }}
  .raw-table tbody tr.hidden {{ display: none; }}
  .raw-table td {{
    padding: .25rem .6rem;
    vertical-align: top;
    border-bottom: 1px solid #f1f5f9;
    max-width: 700px;
  }}
  .raw-table td span {{ white-space: pre-wrap; font-family: monospace; font-size: .75rem; }}
  mark {{ background: #fef08a; border-radius: 2px; padding: 0 1px; }}
</style>
</head>
<body>

<div class="report-header">
  <svg class="rh-logo" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="40" height="40" rx="10" fill="url(#rhlg)"/>
    <defs>
      <linearGradient id="rhlg" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="#0ea5e9"/>
        <stop offset="100%" stop-color="#0369a1"/>
      </linearGradient>
    </defs>
    <rect x="10" y="10" width="14" height="2" rx="1" fill="rgba(255,255,255,.35)"/>
    <rect x="10" y="14" width="10" height="2" rx="1" fill="rgba(255,255,255,.25)"/>
    <polyline points="8,26 13,26 16,19 19,31 22,23 25,26 32,26"
      stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  </svg>
  <div class="rh-brand">
    <div class="rh-name"><span class="logi">Logi</span><span class="lyzer">Lyzer</span></div>
  </div>
  <span class="rh-meta">{len(log_files)} file{"s" if len(log_files) != 1 else ""} analysed</span>
</div>

<div class="layout">

  <nav class="sidebar">
    <div class="sidebar-filter-block">
      <label for="global-search">Search</label>
      <input type="search" id="global-search" placeholder="Filter log rows…" oninput="applyFilters()">
      <div class="level-toggles">
        <button class="lvl-btn on" data-lvl="ERROR" onclick="toggleLevel(this)">ERROR</button>
        <button class="lvl-btn on" data-lvl="WARN"  onclick="toggleLevel(this)">WARN</button>
        <button class="lvl-btn on" data-lvl="INFO"  onclick="toggleLevel(this)">INFO</button>
        <button class="lvl-btn on" data-lvl="DEBUG" onclick="toggleLevel(this)">DEBUG</button>
        <button class="lvl-btn on" data-lvl="TRACE" onclick="toggleLevel(this)">TRACE</button>
      </div>
    </div>
    <div class="sidebar-title">Log Files</div>
    {nav_items}
  </nav>

  <div class="main" id="main">
    {time_note}
    {sections}
  </div>

</div>

<script>
  // ── Nav / scroll-spy ──────────────────────────────────────
  function activate(el) {{
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    el.classList.add('active');
  }}

  const main = document.getElementById('main');
  const navItems = Array.from(document.querySelectorAll('.nav-item'));

  function onScroll() {{
    const scrollTop = main.scrollTop;
    let active = 0;
    navItems.forEach((a, i) => {{
      const sec = document.querySelector(a.getAttribute('href'));
      if (sec && sec.offsetTop - main.offsetTop <= scrollTop + 80) active = i;
    }});
    navItems.forEach((n, i) => n.classList.toggle('active', i === active));
  }}
  main.addEventListener('scroll', onScroll, {{ passive: true }});
  onScroll();

  // ── Filtering ─────────────────────────────────────────────
  function toggleLevel(btn) {{
    btn.classList.toggle('on');
    applyFilters();
  }}

  function applyFilters() {{
    const globalNeedle = (document.getElementById('global-search').value || '').toLowerCase();
    // Levels that are ON — empty set means the buttons section is irrelevant (all off = show all)
    const activeBtns = Array.from(document.querySelectorAll('.lvl-btn'));
    const onLevels   = new Set(activeBtns.filter(b => b.classList.contains('on')).map(b => b.dataset.lvl));
    const allOn      = onLevels.size === activeBtns.length;

    document.querySelectorAll('.raw-table').forEach(tbl => {{
      const tableId     = tbl.id;
      const container   = tbl.closest('.raw-log');
      const sel         = container ? container.querySelector('.raw-thread-select') : null;
      const localInput  = container ? container.querySelector('.raw-search') : null;
      const threadFilter = sel       ? sel.value.trim()          : '';
      const localNeedle  = localInput ? localInput.value.toLowerCase().trim() : '';
      let visible = 0;

      tbl.querySelectorAll('tbody tr').forEach(tr => {{
        const level  = (tr.dataset.level  || '').toUpperCase();
        const thread = (tr.dataset.thread || '');
        const text   = tr.textContent.toLowerCase();

        // Level: if all on (default) skip check; otherwise row must match an active level
        const levelOk  = allOn || !level || onLevels.has(level);
        const threadOk = !threadFilter || thread.trim() === threadFilter;
        const globalOk = !globalNeedle || text.includes(globalNeedle);
        const localOk  = !localNeedle  || text.includes(localNeedle);

        const show = levelOk && threadOk && globalOk && localOk;
        tr.classList.toggle('hidden', !show);
        if (show) visible++;

        // Highlight best available needle in message cell
        const msgTd = tr.querySelector('td:last-child span');
        if (msgTd) {{
          const needle = localNeedle || globalNeedle;
          const raw = msgTd.getAttribute('data-raw') || msgTd.textContent;
          msgTd.setAttribute('data-raw', raw);
          if (needle && show) {{
            const lo = raw.toLowerCase(), idx = lo.indexOf(needle);
            if (idx >= 0) {{
              msgTd.innerHTML =
                _esc(raw.slice(0, idx)) +
                '<mark>' + _esc(raw.slice(idx, idx + needle.length)) + '</mark>' +
                _esc(raw.slice(idx + needle.length));
              return;
            }}
          }}
          msgTd.textContent = raw;
        }}
      }});

      const countEl = document.getElementById(tableId + '-count');
      if (countEl) countEl.textContent = visible.toLocaleString() + ' rows';
    }});
  }}

  // ── Sorting ───────────────────────────────────────────────
  const _sortState = {{}};  // tableId -> {{ col, asc }}

  function sortTable(tableId, col) {{
    const tbl  = document.getElementById(tableId);
    const prev = _sortState[tableId] || {{ col: -1, asc: true }};
    const asc  = prev.col === col ? !prev.asc : true;
    _sortState[tableId] = {{ col, asc }};

    // Update header icons
    tbl.querySelectorAll('thead th').forEach((th, i) => {{
      th.classList.remove('sort-asc', 'sort-desc');
      const icon = th.querySelector('.sort-icon');
      if (i === col) {{
        th.classList.add(asc ? 'sort-asc' : 'sort-desc');
        if (icon) icon.textContent = asc ? ' ↑' : ' ↓';
      }} else {{
        if (icon) icon.textContent = ' ⇅';
      }}
    }});

    const tbody = tbl.querySelector('tbody');
    const rows  = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {{
      const ta = (a.cells[col] ? a.cells[col].textContent : '').trim();
      const tb = (b.cells[col] ? b.cells[col].textContent : '').trim();
      // Numeric sort if both look like numbers
      const na = parseFloat(ta), nb = parseFloat(tb);
      const cmp = (!isNaN(na) && !isNaN(nb)) ? na - nb : ta.localeCompare(tb);
      return asc ? cmp : -cmp;
    }});

    rows.forEach(r => tbody.appendChild(r));
  }}

  function _esc(s) {{
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }}
</script>
</body>
</html>"""
