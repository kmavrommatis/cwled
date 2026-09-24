# GEMINI.md - CWLed Project Reference & Guidelines

**CWLed** is a desktop application for creating and editing [Common Workflow Language (CWL)](https://www.commonwl.org/) documents. It provides a visual, form-based interface alongside a raw CWL code editor, simplifying the design and troubleshooting of computational pipelines.

---

## 1. Project Overview & Architecture

CWLed is built with **Python 3.10+** using **PyQt6** for its cross-platform GUI. It adheres to a modular design, decoupling core CWL parsing logic, visual UI widgets, configuration management, and LLM integrations.

### System Architecture Layout

```
                  ┌──────────────────────────────────────────────┐
                  │                 cwled.py                     │
                  │             (Launcher Entry)                 │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │                cwled/main.py                 │
                  │             (App Initialization)             │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │            cwled/MainWindow.py               │
                  │         (Tabs: Info, App, Code, Graph)       │
                  └──────────┬───────────┬────────────┬──────────┘
                             │           │            │
                             ▼           ▼            ▼
                  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐
                  │ CWLparser.py│ │   widgets/  │ │    LLM.py    │
                  │ (Parse/Save)│ │(Custom Forms│ │ (LangChain/  │
                  └─────────────┘ │   & Inputs) │ │ AI Assistant)│
                                  └─────────────┘ └──────────────┘
```

### Key Functional Areas
1. **Core Launcher & Setup (`cwled.py` & `cwled/main.py`)**: Boots the PyQt6 application, parses CLI arguments (e.g., input files, workspaces), sets appropriate operating system stylesheets, and initializes logging.
2. **Main Application Window (`cwled/MainWindow.py`)**: Houses the primary visual tabs:
   - **Info**: Global metadata (ID, version, label, documentation).
   - **App / Form Editor**: Graphical input forms for commandline arguments, inputs, outputs, requirements, and secondary files.
   - **Code**: A synchronous YAML/JSON editor using Python or custom JavaScript text elements.
   - **Network Graph / Visual Builder**: An interactive graph visualization (`NetworkGraph.py`) showing node links and workflow structure.
3. **CWL Parser & Model (`cwled/CWLparser.py`, `cwled/cwl_utils_handler.py`)**: Interacts with raw YAML/JSON representations of CWL files. Ensures that programmatic changes to form widgets translate into valid schema-conformant structures.
4. **LLM Integration (`cwled/LLM.py`)**: Provides optional agentic helpers (using LangChain and system prompts located in `resources/config/`) to troubleshoot code or automatically draft tools from descriptive documentation.
5. **Configuration Subsystem (`cwled/configuration.py`)**: Reads and manages configurations in `cwled.yaml` located in the OS-specific user configuration directory (e.g., `~/Library/Application Support/cwled/` on macOS).

---

## 2. Directory Structure

```
cwled/
├── cwled.py                       # Root launcher script
├── setup.py                       # Package packaging and script installation
├── requirements.txt               # Main runtime dependencies
├── cwled.spec                     # PyInstaller specification for desktop bundle
├── DEV.md                         # Internal development and release guide
├── NOTES.txt                      # Release-specific notes and active version tracker
├── cwled/                         # Main Python package
│   ├── main.py                    # Qt application initialization and CLI parsing
│   ├── MainWindow.py              # Main UI layout orchestration and Tab managers
│   ├── CWLparser.py               # Core parser translating YAML/JSON into editor models
│   ├── LLM.py                     # Integration layer with LLM services via LangChain
│   ├── configuration.py           # Configuration reader/writer for cwled.yaml
│   ├── logger.py                  # Standardized color-coded logging module
│   ├── widgets/                   # Folder housing custom PyQt reusable form controls
│   │   ├── qInputs.py             # Form management for tool inputs
│   │   ├── qOutputs.py            # Form management for tool outputs
│   │   ├── qArguments.py          # Visual table for CLI arguments
│   │   └── ...                    # Specific configuration sub-widgets (Docker, EnvVar, secondary files)
├── resources/                     # Asset bundle
│   ├── icons/                     # UI buttons, badges, and logo graphics
│   ├── config/                    # Default configurations and LLM JINJA2 prompts
│   └── ontologies/                # EDAM bioinformatics ontologies for metadata validation
├── docs/                          # Developer user guides, UI screenshots, and specifications
└── tests/                         # Sandbox and test suite of various valid/invalid CWL scenarios
```

---

## 3. Technology Stack & External Dependencies

The application relies on native package managers and the following external tools/libraries:

*   **GUI Framework**: `PyQt6` and `qtpy` (for Qt wrapper abstractions).
*   **CWL Engine & Validation**: `cwltool` for execution and native syntax verification.
*   **Node.js**: Critical for evaluating standard CWL JavaScript expressions.
*   **Format Utility**: `cwl-explode` (`cwlformat`) for structure formatting.
*   **LLM Service Client**: `LangChain` wrapper models (compatible with OpenAI, Anthropic, or Google APIs).

---

## 4. Coding & Architectural Conventions

To maintain codebase health and consistency, adhere to these guidelines during contributions:

### Design Principles
1. **Model-View Synchronization**: The data representation of the open CWL file is maintained dynamically. Ensure edits in any visual widget (e.g., arguments list or Docker configurations) instantly update the internal `CWLparser` model state, synchronizing with the raw code view in real-time.
2. **Explicit Type Safety**: Prefer explicit type declarations and PyQt6 type conversions. Do not bypass or suppress type checkers or linters unless absolutely necessary.
3. **Structured Logging**: Always use the color-coded logger from `cwled/logger.py`. Log structural/state transitions with `logger.debug` or `logger.info`, and failures with `logger.error` or `logger.exception`.
4. **Clean Destructuring & Composition**: Prioritize composition and delegation (e.g., custom widgets delegating their state updates back to parent controllers) instead of complex multi-level inheritance hierarchies.

---

## 5. Development & Testing Workflow

### Running the Editor Locally

```bash
# Set up environment
conda create --name cwled python=3.10
conda activate cwled
pip install -r requirements.txt

# Run in development mode
python cwled.py
```

### Manual Verification Checklist
When modifying GUI components, verify key behaviors across these categories:

1. **Workspace Controls**:
   * Changing the workspace updates file filters and triggers a directory refresh.
   * Sorting files by name or date behaves correctly.
2. **Form Interaction**:
   * Adding, deleting, and moving arguments updates command-line previews.
   * Modifying input file formats or adding secondary files works smoothly without freezing the UI.
3. **Code Tab**:
   * Switch tabs to check if direct edits to YAML/JSON syntax propagate cleanly to input fields in the "App" tab.
4. **Validation**:
   * Use `cwltool --validate` outputs to verify that generated schemas are compliant.
