# Logging

This document describes how CWLed logs messages, how external libraries are logged, and how log messages are shown in dialog boxes and message boxes.

## 1. Core setup

Logging uses Python's standard `logging` module. The root logger is configured once, when `cwled/logger.py` is imported. `cwled/main.py` imports it early, before any other CWLed module logs.
Always use the color-coded logger from `cwled/logger.py`. Log structural/state transitions with `logger.debug` or `logger.info`, and failures with `logger.error` or `logger.exception`.

### Root logger

`cwled/logger.py` sets the root logger (`logging.getLogger('')`) to `DEBUG` and attaches three handlers:

- **Console handler** (`LevelBasedFormatter`): writes to stderr. The formatter depends on the record level. DEBUG and ERROR/CRITICAL use the detailed format (line number and file name). INFO and WARNING use the basic format. Both formats are coloured with `colorlog`.
- **File handler** (created by `setup_file_handler()`): writes DEBUG and above to `cwled_<YYYYmmdd_HHMMSS>.log` in the user log directory returned by `platformdirs.user_log_path('cwled')`. A new file is created on every launch, and its path is logged at INFO. The file uses a plain-text formatter without colours.
- **Error dialog handler** (`ErrorDialogHandler`): added to the root logger once, by the main window at start-up (`MainWindow.setupGlobalErrorDialogLogging()`). The method does nothing if a handler is already attached, so only one instance is ever installed. See section 3.

### Per-class loggers

Most classes create their own logger in `__init__`:

```python
self.logger = logging.getLogger(self.__class__.__name__)
```

Some classes also create sub-loggers for specific activities, for example `TabToolEditor` (`TabToolEditor.requirements`, `TabToolEditor.inputs`) and `NetworkGraph` / `GraphNodes` (`NetworkGraph_addnodes`, `GraphNodes_edges`). Module-level code uses `logging.getLogger(__name__)`.

### Levels from configuration

Each class sets its own level from the `logLevel` map in `cwled.yaml`, with `DEBUG` as the default:

```python
self.logger.setLevel(data.configuration.get('logLevel', {}).get(self.__class__.__name__, 'DEBUG'))
```

Keys in `logLevel` are logger names, so sub-loggers can be set separately (for example `TabToolEditor.inputs`). The Logging tab of the configuration dialog (`cwled/ConfigDialog.py`, `createLoggingTab`) lists these keys and edits them.

Accepting the configuration dialog applies the new levels to some loggers straight away and to others only later. See "Changing levels" below.

### Changing levels

The Logging tab of the configuration dialog edits the `logLevel` map. Accepting the dialog does three things:

1. `ConfigDialog.accept()` (`cwled/ConfigDialog.py`) writes the chosen levels into `data.configuration` and saves them to `cwled.yaml`. The change therefore persists across restarts.
2. `MainWindow.onMenuConfiguration()` (`cwled/MainWindow.py`) calls `setLevel()` on the main window's logger and on the `logger` of every open child window in `open_windows`. The level is read from `data.configuration`.
3. Nothing else is re-read. Third-party loggers are not touched (see below).

The table shows which loggers change when the dialog is accepted:

| Logger | Changes on accept? |
|---|---|
| The main window's logger (`MainWindow`) | Yes |
| The logger of each open child window (`ChildWindow`) | Yes |
| Child windows opened after the change | Yes. They read the configuration in their constructor. |
| Sub-loggers of an open window (for example `TabToolEditor.inputs`, `NetworkGraph_addnodes`) | No. They keep their old level until the window is re-created or the application restarts. |
| Loggers of tab and widget objects inside a window (for example `TabToolEditor`, `TabCodeEditor`, `WorkspaceContents`) | No. Same as above. |
| Third-party loggers (section 2) | No. See below. |

Things to know:

- **Only keys already in `logLevel` are listed.** The dialog builds its rows from the `logLevel` entries that exist in the configuration. A logger name that is not in `cwled.yaml` has to be added to the file by hand before the dialog shows it. Once it is in the file, the dialog can change it.
- **Third-party levels are not updated on accept.** `pinThirdPartyLoggers()` reads `logLevel` again only at these points: at import of `cwled/logger.py`, at start-up in `main.py` after the configuration is loaded, in `CWLRunner.checkTools()`, and after each in-process cwltool run. A changed level for cwltool's loggers therefore takes effect the next time one of these points runs. A changed level for any other library takes effect after a restart.
- **Defaults for missing keys vary.** When a class has no entry in `logLevel`, most classes use `DEBUG`. Some use a different default in code: `TemplateEditorDialog` and `QCWLedWidget` use `INFO`, the module-level logger in `CWLparser.py` uses `WARNING`, and `JavascriptEditor` always sets `DEBUG` and ignores `logLevel`.

### How a level is applied to a record

A log record passes two checks:

1. **The level of the logger that created it.** Only that logger's level is checked. Parent loggers' levels are not checked again as the record propagates up to the root. So a logger set to `CRITICAL` also drops its ERROR records, and those records never reach the error dialog handler.
2. **The level of each handler that receives it.** The console and file handlers accept DEBUG and above. The error dialog handler accepts ERROR and CRITICAL. This level is fixed in code and is not configurable.

Loggers without a level of their own inherit the root logger's level, which is `DEBUG`. CWLed sets a level on every logger it creates, so the root level only affects loggers that CWLed does not configure. These are libraries whose names are not in `THIRD_PARTY_LOGGERS`.

### Colour conventions

The console colours come from `log_colors` in `cwled/logger.py`:

| Level | Colour |
|---|---|
| DEBUG | cyan |
| INFO | light white |
| WARNING | yellow |
| ERROR | red |
| CRITICAL | bold red |

## 2. External libraries

Third-party loggers would otherwise flood the log, because they propagate to the DEBUG root logger. `cwled/logger.py` handles this as follows.

- `THIRD_PARTY_LOGGERS` lists the logger names of third-party libraries that CWLed uses, such as `urllib3`, `requests`, `cwltool`, `cwl_utils`, `salad`, `rdflib`, `boto3`, `langchain` and `openai`.
- `pinThirdPartyLoggers()` sets each of these loggers to `WARNING`. A name in the `logLevel` map overrides this default, so a library can be raised for debugging:

  ```yaml
  logLevel:
    urllib3: DEBUG
  ```

- A library can reset its own logger when it is imported, so the pin is applied again at these points:
  - at import of `cwled/logger.py`;
  - in `CWLRunner.checkTools()` (`cwled/CWLtoolFactory.py`), after the in-process tools are imported. `cwltool` sets its own logger to INFO on import;
  - after each in-process `cwltool` run in `CWLRunner._runCwltool()`.

### In-process cwltool output

`CWLRunner._runCwltool()` runs `cwltool.main.main()` in-process. It passes its own `logging.StreamHandler`, which writes to a `StringIO` buffer, as `logger_handler`. This has two effects:

- cwltool does not call `coloredlogs.install()`, so its logger level is not reset on each run;
- cwltool's log records go into the buffer. The buffer is returned as `CWLRunner.stderr`, and the UI shows it when validation, upgrade or template generation fails.

After the run, the handler is removed from the `cwltool` and `salad` loggers, so later runs do not write into the old buffer.

Subprocess-based tools are not covered by the handler above. They are read through their stdout and stderr pipes in `CWLtoolFactory.py`.

## 3. Showing log messages in dialogs and message boxes

Log messages reach the user in three ways.

### 3.1 Automatic: error log records open a dialog

`ErrorDialogHandler` (`cwled/logger.py`) is a `logging.Handler` that handles ERROR and CRITICAL records. The main window attaches it to the root logger in `MainWindow.setupGlobalErrorDialogLogging()` (`cwled/MainWindow.py`).

For each ERROR or CRITICAL record, `emit()`:

1. formats the message in the thread that logged it;
2. emits a Qt signal, `showRequested`, on a `_ErrorDialogBridge` object. The bridge is created in the handler's constructor and lives on the GUI thread.

The bridge's slot runs on the GUI thread. It shows an `ErrorDialog` (`cwled/widgets/qButtons.py`) with the title `Error from <logger name>` or `Critical Error from <logger name>`. The dialog body contains the logger name, the level and the formatted message. The dialog is modal and `exec()` blocks until it is closed.

Because the bridge lives on the GUI thread, a record logged from a worker thread, such as the LLM request thread in `llm_jobs.py`, is delivered as a queued call. The dialog is created on the GUI thread, from the event loop, so it appears a little after the log call. A record logged on the GUI thread is delivered directly, as before.

As a result, any `logger.error(...)`, `logger.exception(...)` or `logger.critical(...)` call in the application shows a dialog, whichever thread makes it. WARNING and lower records do not.

The handler must be created on the GUI thread, because the bridge is created in its constructor. `MainWindow` does this at start-up. The `parent_window` argument is stored, but `ErrorDialog` does not take a parent, so it is not used for display.

### 3.2 Explicit: code shows an error dialog

Some code paths build the dialog directly. They also include details that a log line does not carry, such as cwltool's captured stderr or a traceback:

- `ErrorDialog(error_message, details, title)` (`cwled/widgets/qButtons.py`) is used in `ChildWindow.py` (validation, troubleshooting and tool-creation errors) and `TabCodeEditor.py`. The details text is cleaned of ANSI escape codes and control characters before display.
- `QErrorMessage` (`cwled/qErrorMessage.py`) provides two static helpers that use a `QMessageBox`:
  - `show_critical(parent, title, message, exception=None, logger=None)` logs the message at CRITICAL, with the traceback at DEBUG if an exception is given, and then shows the message box;
  - `show_and_raise(...)` calls `show_critical` and then re-raises the exception unless `raise_exception=False`.
  
  These are used in `TabToolEditor.py` and `TabCodeEditor.py`.

### 3.3 Plain message boxes

Confirmations and simple notices use `QMessageBox` directly, without logging. Examples are the reset and remove confirmations and warnings in `ConfigDialog.py`, the JSHint error in `JavascriptEditor.py` and the template errors in `TemplateEditorDialog.py`.

## 4. Using the logger in new code

- Get the logger in the class's `__init__` with `logging.getLogger(self.__class__.__name__)`, and set its level from `logLevel`, following the existing classes.
- Log state changes and structural events at `DEBUG` or `INFO`.
- Log failures at `ERROR`, or use `logger.exception(...)` inside an `except` block. Be aware that this opens an error dialog (section 3.1).
- Do not add a new `StreamHandler` or `basicConfig` call. The root logger is already configured by `cwled/logger.py`.
- If a new third-party library writes too much to the log, add its logger name to `THIRD_PARTY_LOGGERS` in `cwled/logger.py`.
