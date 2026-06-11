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


def _build_report(
    log_files: list[LogFile],
    sections_html: list[str],
    time_from: Optional[str],
    time_to: Optional[str],
) -> str:
    time_note = ""
    if time_from or time_to:
        time_note = f"<p class='time-filter'>Time filter: {time_from or '—'} → {time_to or '—'}</p>"

    filenames = ", ".join(lf.filename for lf in log_files)
    sections = "\n".join(sections_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Logi Report Analysis</title>
<style>
  body {{ font-family: sans-serif; margin: 0; background: #f5f5f5; color: #222; }}
  .report-header {{ background: #1a3a5c; color: #fff; padding: 1.5rem 2rem; }}
  .report-header h1 {{ margin: 0 0 .25rem; font-size: 1.4rem; }}
  .report-header p {{ margin: 0; font-size: .85rem; opacity: .8; }}
  .time-filter {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px;
                  padding: .4rem .8rem; margin: 1rem 2rem; font-size: .85rem; }}
  .section {{ background: #fff; margin: 1rem 2rem; border-radius: 6px;
              box-shadow: 0 1px 3px rgba(0,0,0,.1); padding: 1.5rem; }}
  .section h2 {{ margin-top: 0; font-size: 1.1rem; border-bottom: 2px solid #1a3a5c;
                 padding-bottom: .5rem; }}
  .badge {{ background: #e8eef4; color: #1a3a5c; border-radius: 3px;
            padding: 2px 6px; font-size: .75rem; font-weight: normal; }}
  .section.error h2 {{ border-color: #dc3545; }}
  .section.unsupported {{ opacity: .7; }}
  .stat-cards {{ display: flex; flex-wrap: wrap; gap: .75rem; margin-bottom: 1rem; }}
  .stat-card {{ background: #f0f4f8; border-radius: 4px; padding: .6rem 1rem; min-width: 140px; }}
  .stat-card .label {{ font-size: .75rem; color: #666; }}
  .stat-card .value {{ font-size: 1.2rem; font-weight: 600; color: #1a3a5c; }}
</style>
</head>
<body>
<div class="report-header">
  <h1>Logi Report — Log Analysis</h1>
  <p>Files: {filenames}</p>
</div>
{time_note}
{sections}
</body>
</html>"""
