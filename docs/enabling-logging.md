# Enabling Logi Report Logging

> Official reference: [Configuring Logi Report Logging System](https://devnet.logianalytics.com/hc/en-us/articles/4405690489111-Configuring-Logi-Report-Logging-System)

---

## Log file locations

| Setting | Default |
|---------|---------|
| Log directory | `<install_root>\logs` |
| Config file | `<install_root>\bin\LogConfig.properties` |
| UI config | Server Console → **Administration → Configuration → Log** |

Log files are named after their category: `Engine.log`, `Error.log`, `Access.log`, etc.

---

## Log types

| File | What it captures |
|------|-----------------|
| `Engine.log` | Report execution, creation, export |
| `DHTML.log` | Interactive viewer (DHTML) client–server actions |
| `Access.log` | User access, HTTP requests, task scheduling |
| `Error.log` | Errors across all categories |
| `Event.log` | Server lifecycle (startup, shutdown) |
| `Debug.log` | SQL statements, detailed debug traces |
| `Performance.log` | Report and export timing analysis |
| `Dump.log` | Task queue lifecycle (submit, run, finish) |
| `Manage.log` | Server Console and `server.properties` changes |
| `PageReport.log` | Page report modifications, Ad Hoc, Studio |

---

## Log levels

From least to most verbose:

| Level | Captures |
|-------|---------|
| `OFF` | Nothing |
| `FATAL` | Severe errors causing abort |
| `ERROR` | Errors that allow continued operation |
| `WARN` | Potentially harmful situations |
| `OUTLINE` | Program workflow outline |
| `INFO` | Application progress, important variables |
| `TRIVIAL` | Fine-grained tracing |
| `ALL` | Everything |

**Recommended starting level:** `INFO` for production, `DEBUG` or `ALL` when troubleshooting.

---

## Configuring via Server Console (UI)

1. Open **Server Console** → **Administration** → **Configuration** → **Log**
2. Select the log category (Engine, Error, Access, etc.)
3. Set the **Log Level** and **Appender** (RollingFile recommended)
4. Set **File Name** — use an absolute path if you want logs outside the install directory (e.g. `E:\logs\Engine.log`)
5. Save and restart the server

---

## Configuring via LogConfig.properties

Edit `<install_root>\bin\LogConfig.properties` directly for scripted or bulk changes.

### Enable a log category at INFO level (RollingFile)

```properties
# Engine log
log4j.logger.Engine=INFO, EngineAppender
log4j.appender.EngineAppender=org.apache.log4j.RollingFileAppender
log4j.appender.EngineAppender.File=<install_root>/logs/Engine.log
log4j.appender.EngineAppender.MaxFileSize=50MB
log4j.appender.EngineAppender.MaxBackupIndex=5
log4j.appender.EngineAppender.layout=org.apache.log4j.PatternLayout
log4j.appender.EngineAppender.layout.ConversionPattern=%m [%t][%p][%d{{dd MM yyyy HH:mm:ss,SSS}}]%n
```

Replace `Engine` / `EngineAppender` / `Engine.log` with the relevant category name for other log types.

> **Note:** Avoid `%C`, `%F`, `%L`, `%M` in the pattern — they use reflection and hurt performance.

### Daily rotation instead of size-based

```properties
log4j.appender.EngineAppender=org.apache.log4j.DailyRollingFileAppender
log4j.appender.EngineAppender.DatePattern='.'yyyy-MM-dd
```

---

## Rotation and retention

| Property | Purpose |
|----------|---------|
| `MaxFileSize` | Max size before rotation (e.g. `50MB`, `100MB`) |
| `MaxBackupIndex` | Number of rotated files to keep (e.g. `5` keeps last 5) |
| `DatePattern` | For DailyRollingFile — controls rotation frequency |

---

## Command-line overrides (startup flags)

These flags override `LogConfig.properties` at server start:

| Flag | Effect |
|------|--------|
| `-vDebug` | Engine → file at `INFO` level |
| `-vError` | Engine → file at `ERROR` level |
| `-logall` | All loggers → `INFO` level |
| `-log[:fileName]` | Engine → specified file at `DEBUG` level |

---

## Organisation-specific logging

If Organisations are enabled, each organisation gets its own log subfolder under `<install_root>\logs`. Enable the **Additivity** option in the log config to also propagate entries to the root appenders.

---

## Tips for collecting logs for this tool

- Enable at least **Engine**, **Error**, **DHTML**, **Access**, and **Dump** at `INFO` or higher
- Use **RollingFile** with `MaxFileSize=50MB` and `MaxBackupIndex=3` to avoid disk pressure
- Collect logs during a representative workload period (a few minutes to hours)
- Upload all relevant `.log` files together — this tool correlates events across files by timestamp
