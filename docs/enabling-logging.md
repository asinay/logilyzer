# Enabling Logi Report Logging

> Official reference: [Configuring Report Logging System](https://docs-report.zendesk.com/hc/en-us/articles/28891504465549-Configuring-Report-Logging-System)

Use this guide when a customer hasn't enabled logging and you need log files to diagnose an issue. Send them the relevant section, or walk through it with them on a call.

---

## Where log files live

| Item | Default path |
|------|-------------|
| Log output directory | `<install_root>\logs` |
| Advanced config file | `<install_root>\bin\LogConfig.properties` |
| UI configuration | Server Console → **Administration → Configuration → Log** |

Log files are named after their category: `Engine.log`, `Error.log`, `Access.log`, etc.  
Custom paths are supported — the customer can point a log to `E:/logs/Engine.log` for example.

---

## Minimum recommended set for support

Ask the customer to enable **all five** of these at `INFO` level before reproducing the issue:

| Log type | File | What it captures |
|----------|------|-----------------|
| **Engine** | `Engine.log` | Report run/export events and elapsed times |
| **DHTML** | `DHTML.log` | Action costs — critical for performance issues |
| **Error** | `Error.log` | All errors across every log category |
| **Access** | `Access.log` | HTTP requests/responses and session activity |
| **Dump** | `Dump.log` | Task queue lifecycle (submitted / running / waiting) |

Add these if the issue is specific to them:

| Log type | When to add |
|----------|------------|
| **Debug** | SQL queries, low-level tracing |
| **Performance** | Export performance detail |
| **Page Report** | Page Report Studio issues |
| **Manage** | Server Console / settings changes |
| **Event** | Server start/stop events |

---

## Configuring via Server Console

1. Go to **Administration → Configuration → Log**
2. From **Log Type**, select the log category
3. From **Log Level**, select `INFO` (use `DEBUG` or `ALL` only when actively troubleshooting — they fill disk fast)
4. Set **Additivity** to `True` if child loggers should inherit appenders from parent loggers
5. Select an appender type and fill in settings (see below)
6. Click **Save**

Repeat for each log type needed.

---

## Log levels

| Level | What is logged |
|-------|---------------|
| `OFF` | Nothing — disables the log |
| `FATAL` | Severe errors causing abort |
| `ERROR` | Errors that allow continued operation |
| `WARN` | Potentially harmful situations |
| `OUTLINE` | Program workflow outline |
| `INFO` | Application progress — **recommended for support** |
| `TRIVIAL` | Fine-grained trace events |
| `ALL` | Everything |

---

## Appender types

### RollingFile *(recommended)*

Rotates to a new file when size exceeds the configured maximum. Best for production and support collection.

| Setting | Recommended value | Notes |
|---------|------------------|-------|
| **Layout Type** | `Pattern` | |
| **File Name** | `<install_root>\logs\<Type>.log` | Use absolute path to save elsewhere |
| **Append** | `True` | Keeps history across restarts |
| **Buffered IO** | `True` | Better I/O performance |
| **Maximum File Size** | `50MB` | Adjust down if disk is tight |
| **Maximum Backup Index** | `3` | Keeps 3 rotated copies |

> **Avoid** conversion characters `%C`, `%F`, `%L`, `%M` in Pattern layouts — they use reflection and slow down logging significantly.

### File

Same as RollingFile without rotation — grows indefinitely. Avoid unless disk space is not a concern.

### DailyRollingFile

Rotates daily. Same settings as File, plus **Date Pattern** (e.g. `'.'yyyy-MM-dd`).

### Socket / Syslog / Console

Remote or stream logging. Rarely needed for support collection — use RollingFile instead.

---

## Collecting logs for this tool

1. Enable the recommended log types above at `INFO` level with a `RollingFile` appender
2. Reproduce the issue (or capture during a representative workload period)
3. Collect **all** `.log` files from `<install_root>\logs\`  
   — if the customer has multiple organisations, check each org's subfolder too
4. Upload everything to the parser in one batch — it correlates events across files by timestamp

The tool auto-detects log type from the filename, so the standard naming must be intact (`Engine.log`, `Access.log`, etc.).
