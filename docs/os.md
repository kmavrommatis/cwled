# OS-Specific Behaviors and Platform Customizations

This document serves as a comprehensive reference of all OS-specific integrations and customizations implemented in the **CWLed** (Common Workflow Language Editor) application to ensure a native look, feel, and performance on both macOS (`darwin`) and Linux.

---

## 1. Application Styling and Themes
*   **Location:** `cwled/main.py` (`getOStyle()`)
*   **Behavior:**
    *   On macOS, the application sets its Qt application style to `'macOS'` to render using native Apple UI controls.
    *   On Windows, it styles itself with `'Windows'`.
    *   On Linux, it leverages the `'Fusion'` theme which integrates cleanly across GNOME, KDE, and other window managers.

---

## 2. Configuration & Log Directories
*   **Location:** `cwled/configuration.py` (`setUserConfigurationDirectory()`), `cwled/MainWindow.py` (`initUI()`)
*   **Behavior:** Rather than relying on hardcoded relative files or absolute paths, CWLed adheres to platform standards via `platformdirs`:
    *   **macOS:** Configuration is placed in `~/Library/Application Support/cwled/`, and logs reside in `~/Library/Logs/cwled/`.
    *   **Linux:** Configuration is placed in `~/.config/cwled/` (respecting the XDG directory specification), and logs are placed in `~/.cache/cwled/log/`.

---

## 3. macOS Global Menu Bar Fix
*   **Location:** `cwled/MainWindow.py` (`_ensureWindowActive()`, `_refreshMenuBar()`)
*   **Behavior:** On macOS, the menu bar is global and detached from application windows. Switching focus or closing dialogs inside PyQt6 can often cause the global menu to lock, hide, or fail to respond. When a window is focused on macOS, the application programmatically forces a menu bar redraw (`setVisible(False)`, then `setVisible(True)` and `update()`) to maintain menu responsiveness.

---

## 4. Environment `PATH` Resolution for GUI Bundles
*   **Location:** `cwled/CWLtoolFactory.py` (`_resolve_command()`)
*   **Behavior:** Applications launched from the macOS Finder or Dock do not inherit custom terminal `PATH` environments. To prevent failure in resolving system-wide tools (like Homebrew-installed `cwltool`, `node`, or conda/pip tools), CWLed automatically appends platform-specific standard paths to the search list at runtime:
    *   **macOS:** Prepend `/opt/homebrew/bin` and `/usr/local/bin`.
    *   **Linux:** Prepend `~/.local/bin` (commonly used by `pip install --user`), `/usr/local/bin`, and `/usr/bin`.
*   Additionally, the path resolution expands any tilde (`~`) prefixes found in user configurations.

---

## 5. Cross-Platform Font Fallbacks
*   **Location:** `cwled/main.py`
*   **Behavior:** The default font configured in `cwled.yaml` is often macOS/Windows specific (e.g. `Arial`). Linux machines lacking proprietary MS Core Fonts will default to unpredictable standard alternatives, occasionally breaking margins. CWLed uses standard font fallback arrays:
    *   *Fallbacks:* `[font_family, "Helvetica Neue", "Ubuntu", "DejaVu Sans", "Liberation Sans", "Arial", "sans-serif"]`

---

## 6. Keyboard Shortcuts using Qt Standard Keys
*   **Location:** `cwled/MainWindow.py` (`setMenu()`)
*   **Behavior:** Keyboard shortcuts for main operations utilize Qt's `QKeySequence` system. Rather than hardcoding absolute keystroke combinations, the app binds standard keys which automatically map to platform conventions:
    *   `StandardKey.Open` (Cmd+O on macOS, Ctrl+O on Linux)
    *   `StandardKey.Save` (Cmd+S on macOS, Ctrl+S on Linux)
    *   `StandardKey.SaveAs` (Shift+Cmd+S on macOS, Ctrl+Shift+S on Linux)
    *   `StandardKey.Refresh` (Cmd+R on macOS, Ctrl+R on Linux)
    *   `StandardKey.Preferences` (Cmd+, on macOS, maps to appropriate Menu location on Linux)

---

## 7. Close Window & Save Confirmation Lifecycle
*   **Location:** `cwled/ChildWindow.py` (`closeEvent()`)
*   **Behavior:** Prompting a user to save modified progress before closing is standard, but must support a "Cancel" abort action to prevent accidental data loss. Under the hood:
    *   If modifications exist, the app issues a centered prompt with standard `Yes | No | Cancel` buttons.
    *   If the user selects `Cancel` or closes the confirmation, `event.ignore()` is called, aborting the closing lifecycle and keeping the window open across both operating systems.

---

## 8. Resource Path & Package Packaging
*   **Location:** `cwled/helperFunctions.py` (`getResourcePath()`)
*   **Behavior:** Assets must load cleanly in development as well as packaged binaries:
    *   **PyInstaller frozen build:** Resolves assets via `sys._MEIPASS` or the binary executable parent.
    *   **py2app macOS bundle:** Checks `os.environ['RESOURCEPATH']` to load icons/configs out of the app bundle directory.
    *   **Development:** Falls back to relative paths from the Python source root.

---

## 9. Installer & Bundle Pipelines
*   **Location:** `Makefile`, `setup.py`, `cwled.spec`
*   **macOS targets:**
    *   Creates a standalone `.app` bundle using PyInstaller with full High-DPI support, application file/mime association metadata (mapping `.cwl` files to CWLed), and dark-mode opt-in in `Info.plist`.
    *   Wraps the `.app` bundle inside a native disk image installer `.dmg` file using macOS's `hdiutil` CLI.
*   **Linux targets:**
    *   Builds a Linux-compatible standalone binary and copies all resources to a workspace folder.
    *   Generates a native Linux `run.sh` launcher script setting runtime paths.
    *   Packs the output inside a compressed `.tar.gz` archive for distribution.
