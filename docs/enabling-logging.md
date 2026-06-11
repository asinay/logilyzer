# Enabling Logi Report Logging

> Official reference: [Configuring Report Logging System](https://docs-report.zendesk.com/hc/en-us/articles/28891504465549-Configuring-Report-Logging-System)

---

## Log file locations

| Item | Default |
|------|---------|
| Log output directory | `<install_root>\logs` |
| Config file (advanced) | `<install_root>\bin\LogConfig.properties` |
| UI configuration | Server Console → **Administration → Configuration → Log** |

Log files are named after their category: `Engine.log`, `Error.log`, `Access.log`, etc.

---

## Log types

| Log type | File | What it captures |
|----------|------|-----------------|
| **Engine** | `Engine.log` | Events related to running, creating, and exporting reports |
| **Page Report** | `PageReport.log` | Modifying and saving page reports, Ad Hoc and analysis features in Page Report Studio |
| **Access** | `Access.log` | Which users accessed report running and task scheduling services |
| **Manage** | `Manage.log` | Modifications to settings in Server Console or `server.properties` |
| **Error** | `Error.log` | Errors in any of the log categories |
| **Event** | `Event.log` | Server lifecycle events such as start time and stop time |
| **Debug** | `Debug.log` | Events needed for debugging, e.g. SQL statements used to query the database |
| **Performance** | `Performance.log` | Performance analysis of reports and export operations |
| **Dump** | `Dump.log` | Task lifecycle events: when a task was submitted, when it ran, when the Engine initiated and stopped |

---

## Configuring via Server Console (UI)

1. On the system toolbar of the Server Console, navigate to **Administration → Configuration → Log**
2. From the **Log Type** drop-down, select the log category to configure
3. From the **Log Level** drop-down, select the desired level (see table below)
4. From the **Additivity** drop-down, select **True** if you want child loggers to inherit all appenders from ancestor loggers
5. Select an **Appender** type and configure it (see appender details below)
6. Click **Save**

---

## Log levels

| Level | What is logged |
|-------|---------------|
| `OFF` | Nothing (disables the log) |
| `FATAL` | Severe errors that cause the application to abort |
| `ERROR` | Errors that allow continued operation |
| `WARN` | Potentially harmful situations |
| `OUTLINE` | Program workflow outline |
| `INFO` | Application progress and important variable values |
| `TRIVIAL` | Fine-grained tracing events |
| `ALL` | Everything |

**Recommended:** `INFO` for production. Use `DEBUG` or `ALL` only when actively troubleshooting — these produce large files quickly.

---

## Appender types

### RollingFile *(default — recommended)*

Rotates to a new file when the file exceeds a maximum size.

| Setting | Description |
|---------|-------------|
| **Layout Type** | `Pattern`, `HTML`, `XML`, `TTCC`, or `Simple` |
| **Pattern Conversion** | Conversion pattern (Pattern layout only — see note below) |
| **File Name** | Path to the log file. Default: `<install_root>\logs\<Type>.log`. Use an absolute path to save elsewhere, e.g. `E:/logs/Engine.log` |
| **Append** | `False` to replace the file contents on each server start |
| **Buffered IO** | `True` to buffer log I/O |
| **Maximum File Size** | File size that triggers rotation, e.g. `50MB` |
| **Maximum Backup Index** | Number of rotated files to retain |

> **Performance note:** Avoid conversion characters `%C`, `%F`, `%L`, and `%M` in Pattern layouts — they use reflection to look up caller information and significantly slow down logging.

### File

Same settings as RollingFile, without the size-based rotation.

### DailyRollingFile

Same settings as FileAppender, plus:

| Setting | Description |
|---------|-------------|
| **Date Pattern** | Pattern controlling when the daily rolling file is created, e.g. `'.'yyyy-MM-dd` |

### Socket

Outputs to a remote log server. No layout required.

| Setting | Description |
|---------|-------------|
| **Remote Host** | Hostname of the Socket Server |
| **Port** | Port the Socket Server listens on |
| **Delay** | Timeout interval for socket connection attempts |
| **Location Information** | `True` to include log location in the socket stream |

### Syslog

Outputs to a remote syslog daemon.

| Setting | Description |
|---------|-------------|
| **Layout Type** | `Pattern`, `HTML`, `XML`, `TTCC`, or `Simple` |
| **Syslog Host** | Hostname of the Syslog server |
| **Facility** | Syslog facility name |
| **Facility Printing** | `True` to include facility information in output |

### Console

Outputs to the Java standard stream.

| Setting | Description |
|---------|-------------|
| **Layout Type** | `Pattern`, `HTML`, `XML`, `TTCC`, or `Simple` |
| **Target** | `System.out` (standard output) or `System.err` (standard error) |

---

## Tips for collecting logs for this tool

- Enable at least **Engine**, **Error**, **DHTML**, **Access**, and **Dump** at `INFO` level
- Use **RollingFile** with `MaxFileSize=50MB` and `MaxBackupIndex=3` to avoid disk pressure
- Collect logs during a representative workload period (minutes to hours depending on traffic)
- Upload all relevant `.log` files together — this tool correlates events across files by timestamp
- If Organisations are enabled, each organisation has its own log subfolder under `<install_root>\logs` — collect from all relevant subfolders
