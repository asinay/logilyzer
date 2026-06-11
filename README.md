# Logi Report Logs Parser

Interactive web tool for uploading, visualizing, and exporting analysis of **Logi Report Server** log files.

## What it does

Upload multiple log files at once → get interactive Plotly charts per log type → export a self-contained HTML report. All processing is local; nothing leaves your machine.

**Supported log types and what gets visualized:**

| Log file | Charts & tables |
|----------|----------------|
| `Engine.log` | Operation elapsed times, thread activity, level distribution |
| `DHTML.log` | Action cost over time, slowest-actions table (avg / P95 / max) |
| `Debug.log` | Level distribution over time |
| `Error.log` | Error/warning rate timeline, exception class breakdown, top messages |
| `Access.log` | Request/response volume, HTTP method distribution, top remote IPs |
| `Event.log` | Level distribution over time |
| `Dump.log` | OnDemand & Scheduled task queue depth (Running / Queuing / Waiting) |
| `Performance.log` | Operation elapsed times (same as Engine) |

## Requirements

- Python 3.9+

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Usage

1. **Upload** — drag and drop one or more `.log` files (any mix of log types)
2. **Filter** — optionally set a time range; the UI pre-fills min/max timestamps from your files
3. **Export** — select which files to include, click **Export Report** → downloads a self-contained HTML file with all charts

Log type is detected automatically from the filename. Files with 0 parsed rows (empty or header-only) are shown in the list but produce no charts.

## Output

The exported HTML is fully self-contained (Plotly loaded from CDN). Open it in any browser, no server needed. Reports are also saved locally to `outputs/`.
