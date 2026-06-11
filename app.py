import uuid
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from log_parser import detect_log_type, parse_log_file, LogFile
from analyzers import get_analyzer

app = FastAPI(title="Logi Report Logs Parser")
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
        return await analyzer.analyze(lf, time_from=time_from, time_to=time_to)
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

    # Build sidebar nav items
    nav_items = ""
    for lf in log_files:
        sid = _section_id(lf.filename)
        nav_items += (
            f'<a class="nav-item" href="#{sid}" onclick="activate(this)">'
            f'<span class="nav-dot"></span>'
            f'<span class="nav-label">{lf.filename}</span>'
            f'<span class="nav-badge">{lf.log_type}</span>'
            f'</a>\n'
        )

    sections = "\n".join(sections_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Logi Report Analysis</title>
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
    background: #1a3a5c;
    color: #fff;
    padding: .9rem 1.5rem;
    flex-shrink: 0;
    display: flex;
    align-items: baseline;
    gap: 1.5rem;
  }}
  .report-header h1 {{ font-size: 1.15rem; font-weight: 600; white-space: nowrap; }}
  .report-header p  {{ font-size: .8rem; opacity: .75; }}

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
</style>
</head>
<body>

<div class="report-header">
  <h1>Logi Report — Log Analysis</h1>
  <p>{len(log_files)} file{"s" if len(log_files) != 1 else ""} analysed</p>
</div>

<div class="layout">

  <nav class="sidebar">
    <div class="sidebar-title">Log Files</div>
    {nav_items}
  </nav>

  <div class="main" id="main">
    {time_note}
    {sections}
  </div>

</div>

<script>
  function activate(el) {{
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    el.classList.add('active');
  }}

  // Scroll-spy: highlight nav item whose section is nearest the top
  const main = document.getElementById('main');
  const navItems = Array.from(document.querySelectorAll('.nav-item'));

  function onScroll() {{
    const sections = navItems.map(a => document.querySelector(a.getAttribute('href')));
    const scrollTop = main.scrollTop;
    let active = 0;
    sections.forEach((sec, i) => {{
      if (sec && sec.offsetTop - main.offsetTop <= scrollTop + 80) active = i;
    }});
    navItems.forEach((n, i) => n.classList.toggle('active', i === active));
  }}

  main.addEventListener('scroll', onScroll, {{ passive: true }});
  onScroll();
</script>
</body>
</html>"""
