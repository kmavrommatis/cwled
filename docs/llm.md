# LLM integration

This document describes how CWLed connects to third-party LLM providers, how to configure a provider, and the known limitations of the current implementation. Keep it in sync with any change to the LLM code (see [Keeping this document current](#keeping-this-document-current)).

---

## 1. Overview

CWLed uses the [LangChain](https://python.langchain.com/) chat-model interface. The provider and model are chosen in configuration and created with `langchain.chat_models.init_chat_model`, so the same code path serves Google Gemini, OpenAI, Anthropic, Ollama, OpenRouter, and any OpenAI-compatible local server.

Every LLM call uses the provider and model in the `llm` settings. No feature has its own model name, so changing the AI Assistant tab changes all of them. A call that does not name a model falls back to `LLMModel`, and to `gemini-2.5-flash` only if that key is empty.

LLM features are optional. They are used for these purposes:

| Feature | Menu entry | Class | Dialog / module |
|---|---|---|---|
| Draft a CommandLineTool from pasted help text or documentation | Tools → *Draft CommandLineTool from documentation* | `DraftToolLLM` (`cwled/LLM.py`) | `DraftTool` (`cwled/draft.py`) |
| Generate the documentation of the open tool or workflow | AI button in the Info tab | `DocumentationToolLLM` (`cwled/LLM.py`) | `InfoWindow.onAIButtonPressed` (`cwled/TabInfoWindow.py`) |
| Troubleshoot the open tool or workflow | Troubleshoot menu action | `Troubleshoot` (`cwled/LLM.py`) | `TroubleshootDialog`, `TroubleshootResponseDialog` (`cwled/LLM.py`), called from `ChildWindow.onMenuTroubleshoot` (`cwled/ChildWindow.py`) |

### Source files

| File | Role |
|---|---|
| `cwled/LLM.py` | `BaseLLM` (model setup, template rendering, invocation), `Troubleshoot`, `DraftToolLLM`, troubleshooting dialogs |
| `cwled/draft.py` | `DraftTool` dialog and code-fence cleanup for drafted tools |
| `cwled/llm_jobs.py` | `LLMJob`: runs one LLM request at a time in a background thread and returns the reply to the GUI thread |
| `cwled/llm_providers.py` | Provider list and the API key variable each provider reads |
| `cwled/ConfigDialog.py` | AI Assistant tab: edits the `llm` block and writes the API key to `cwled.env` |
| `cwled/configuration.py` | Loads `cwled.yaml` from the user configuration directory |
| `resources/config/systemPrompt*.jinja2` | System prompts (draft, troubleshoot, tool documentation, workflow documentation) |
| `resources/config/cwled.yaml` | Default configuration, including the `llm` block |

---

## 2. Architecture

```
ConfigDialog (AI Assistant tab) ──writes──▶ cwled.yaml (llm block)
                                 └─writes─▶ cwled.env   (API key)
                                                │
DraftTool / ChildWindow ──▶ DraftToolLLM / Troubleshoot
                                                │  BaseLLM.__init__
                                                ▼
                        resolve key (env → cwled.env) ─▶ init_chat_model(model, model_provider=provider, ...)
                                                │
                       preparePrompt ─▶ invokeModel: [SystemMessage, HumanMessage] ─▶ model.invoke
                                                │
                                        response.content (text)
```

`BaseLLM` (`cwled/LLM.py`) is the shared base class. It:

1. Reads the `llm` block from the loaded configuration.
2. Resolves the API key (see §4).
3. Calls `init_chat_model` with `temperature`, `max_tokens`, and optionally `base_url` and `api_key`.
4. Renders the Jinja2 system prompt from `resources/config/`.
5. Sends one system message and one human message with `model.invoke` and returns the text.

Subclasses only differ in the system prompt they build and the user message they send.

### Feature details

**Draft (`DraftTool` → `DraftToolLLM`)**
- The system prompt is `systemPrompt.jinja2`, rendered with the CWL version, the `sanitize_id` setting, and a tool name guessed from the pasted text (`DraftTool.extractToolName`).
- The pasted text is the user message.
- The request runs in the background. **Draft tool** shows "Drafting..." until the reply arrives, and **Cancel** or closing the dialog drops the reply, so no file is written.
- The reply is passed through `stripCodeFences` and written to `_draft_<tool_name>.cwl` in the current working directory.

**Troubleshoot (`Troubleshoot`)**
- The user describes the issue in `TroubleshootDialog` (`Troubleshoot.askForIssue`). The request then runs in the background, and `TroubleshootResponseDialog` opens when the reply arrives. A new request is refused while one is still running in the same window.
- The system prompt is `systemPrompt-troubleshoot.jinja2`, rendered with the issue description, CWL class, CWL version, and the document itself.
  - For a `Workflow`, the workflow is packed with `CWLRunner.packWorkflow` (remote workflows are first mirrored locally) and the packed YAML is embedded.
  - For a `CommandLineTool`, the document is serialized with `save()` as JSON.
- The user message is fixed: "Please analyze the issue and provide troubleshooting guidance."
- The reply is shown as Markdown in `TroubleshootResponseDialog`, which can save it to a `.md` file.

**Documentation (`DocumentationToolLLM`)**
- Triggered by the AI button in the Info tab (`InfoWindow.onAIButtonPressed`, `cwled/TabInfoWindow.py`). The reply is applied to the description box as described below.
- For a `CommandLineTool` the system prompt is `systemPrompt-tooldoc.jinja2` and the user message is the tool serialized with `save()`.
- For a `Workflow` the system prompt is `systemPrompt-wflowdoc.jinja2`. The step documentation gathered by `Parser.gatherWorkflowDocumentation` is serialized as JSON and added to the user message.
- The model is taken from the `llm` configuration, like the other features. `model` defaults to `None`, so `BaseLLM` reads `LLMModel`.
- The request runs in the background and the AI button is disabled while it runs.
- If the Description still has the text it had when the button was clicked, the reply is written into it. If the user changed the Description meanwhile, the reply is held. The AI button then opens a review dialog with **Replace Description**, **Keep for Later** or **Discard**, so the user's text is never overwritten silently.
- Errors are shown in a message box.

### Execution model

- Each request runs in a background thread (`LLMJob`, `cwled/llm_jobs.py`). Only the preparation runs on the GUI thread: model setup, serializing the CWL document, and the dialogs. The reply returns to the GUI thread through a Qt signal, so widgets are only touched there.
- A reply is used only if its request is still current. Closing the window discards the replies still in flight. Switching tabs does not discard them, because the reply is applied to the current document or held for review.
- The HTTP call itself cannot be interrupted, so Cancel only discards the reply. No timeout is set on provider calls.
- There is no streaming and no retry.
- There is no tool-calling or multi-step agent loop. Each feature is a single request/response.
- The whole document is sent in the prompt, so very large workflows can exceed the model's context window. There is no truncation or size check.

---

## 3. Configuration

### 3.1 Where the settings live

On first run the application copies the default `resources/config/cwled.yaml` into the user configuration directory and loads that copy. The LLM settings are the `llm:` block in that file.

| OS | User configuration directory |
|---|---|
| macOS | `~/Library/Application Support/cwled/` |
| Linux | `~/.config/cwled/` |
| Windows | Under the user's AppData folder, as reported by `platformdirs` |

Both `cwled.yaml` and `cwled.env` live in this directory. You can edit them by hand or through the **AI Assistant** tab of the configuration dialog.

### 3.2 The `llm` block

```yaml
llm:
  provider: google_genai      # which backend to use
  LLMModel: gemini-2.5-flash  # model name for that backend
  base_url: null              # custom endpoint, or null for the provider default
  temperature: 0.1            # 0.0 - 2.0
  max_tokens: 4096            # maximum tokens in the reply
  api_key_env: GOOGLE_API_KEY # name of the environment variable holding the key, or null
```

| Key | Type | Meaning |
|---|---|---|
| `provider` | string | One of `google_genai`, `openai`, `anthropic`, `ollama`, `openrouter`. Passed to `init_chat_model` as `model_provider`. |
| `LLMModel` | string | Model name for the provider. The key is `LLMModel`, with a capital **LLM**. (The README currently says `LLModel`; that is a typo.) |
| `base_url` | string or `null` | Endpoint URL. Leave `null` for the hosted providers. Required for Ollama and for local OpenAI-compatible servers. |
| `temperature` | float | Sampling temperature. Default `0.1`. |
| `max_tokens` | int | Maximum reply length. Default `4096`. |
| `api_key_env` | string or `null` | Name of the environment variable that holds the key. The AI Assistant tab sets it from the provider. If it is missing or `null`, the name is taken from the provider (table in §3.3). Ollama has no key variable. |

> **Note:** the provider names are fixed by the ConfigDialog drop-down. Any other value is passed to LangChain unchanged and will fail unless LangChain knows it.

### 3.3 The API key

The name of the variable depends on the provider, so you do not need to know it in advance. Choosing a provider in the **AI Assistant** tab fills in the name, and the save writes it to `api_key_env`. The mapping is defined in `cwled/llm_providers.py`:

| Provider | Variable read for the key |
|---|---|
| `google_genai` | `GOOGLE_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openrouter` | `OPENROUTER_API_KEY` |
| `ollama` | none (no key needed) |

The key is looked up in this order (`BaseLLM.setModel`, `cwled/LLM.py:84-101`):

1. The process environment variable named by `api_key_env`.
2. The file `cwled.env` in the user configuration directory. If it exists, it is loaded with `load_dotenv` and the variable is read again.

If no key is found and the provider is not local, a *"API Key Missing"* message box is shown and the model is not created. A provider counts as local when `provider` is `ollama`, or when `provider` is `openai` and `base_url` contains `localhost` or `127.0.0.1`.

`cwled.env` uses the standard dotenv format, one `NAME=value` per line:

```bash
GOOGLE_API_KEY=...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

**Entering the key in the UI:** in the **AI Assistant** tab, fill in *API Key Name* and *API Key Value*, then save. The value is written to `cwled.env` (other entries are kept) and also set in the running process, so it takes effect without restarting.

> **Security:** `cwled.env` stores the key in plain text. It is in the user configuration directory, not in the project, so it should never be copied into the repository or into a workspace that is shared.

---

## 4. Provider examples

Each example shows the `llm` block for `cwled.yaml` and the line to add to `cwled.env`. Model names change over time; check the provider's current model list and use any name it accepts in `LLMModel`.

### 4.1 Google Gemini (default)

`cwled.yaml`:

```yaml
llm:
  provider: google_genai
  LLMModel: gemini-2.5-flash
  base_url: null
  temperature: 0.1
  max_tokens: 4096
  api_key_env: GOOGLE_API_KEY
```

`cwled.env`:

```bash
GOOGLE_API_KEY=your-google-api-key
```

### 4.2 OpenAI

`cwled.yaml`:

```yaml
llm:
  provider: openai
  LLMModel: gpt-4o-mini
  base_url: null
  temperature: 0.1
  max_tokens: 4096
  api_key_env: OPENAI_API_KEY
```

`cwled.env`:

```bash
OPENAI_API_KEY=sk-your-openai-key
```

### 4.3 Anthropic

Requires `langchain-anthropic`, which is already a dependency in `pyproject.toml`.

`cwled.yaml`:

```yaml
llm:
  provider: anthropic
  LLMModel: claude-sonnet-5-5
  base_url: null
  temperature: 0.1
  max_tokens: 4096
  api_key_env: ANTHROPIC_API_KEY
```

`cwled.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
```

For a cheaper, faster model, set `LLMModel: claude-haiku-5-5`.

### 4.4 Ollama (local, no key)

> **Dependency:** the `ollama` provider needs the `langchain-ollama` package, which is declared in `pyproject.toml`. Without it, initialization fails with an import error.

Start Ollama and pull a model first, for example `ollama pull llama3.1`.

`cwled.yaml`:

```yaml
llm:
  provider: ollama
  LLMModel: llama3.1
  base_url: http://localhost:11434
  temperature: 0.1
  max_tokens: 4096
  api_key_env: null
```

No line is needed in `cwled.env`. Ollama counts as local, so the key check is skipped.

> **Unverified:** `max_tokens` is passed to every provider. Ollama's chat class may expect `num_predict` instead. If Ollama initialization fails with an unexpected-argument error, remove `max_tokens` from the code path or set the value in the provider's own options. This has not been tested.

### 4.5 Local OpenAI-compatible server (LM Studio, llama.cpp server, vLLM)

These servers speak the OpenAI API, so they use `provider: openai` with a local `base_url`.

`cwled.yaml` (LM Studio's default port shown):

```yaml
llm:
  provider: openai
  LLMModel: your-model-id        # the model identifier shown by the server
  base_url: http://localhost:1234/v1
  temperature: 0.1
  max_tokens: 4096
  api_key_env: OPENAI_API_KEY
```

`cwled.env`:

```bash
OPENAI_API_KEY=lm-studio
```

The server does not check the key, but the OpenAI client needs a value to be present. Because `base_url` contains `localhost`, a missing key does not block the call, but the client may still refuse to start without one. Putting a placeholder in `cwled.env` avoids that.

> **Unverified:** this path is not exercised by any test in the repository.

---

### 4.6 OpenRouter

OpenRouter gives access to models from many vendors through one API key. It uses the `langchain-openrouter` package, declared in `pyproject.toml`. Model names are OpenRouter's `vendor/model` identifiers, for example `openai/gpt-4o-mini` or `anthropic/claude-sonnet-5-5`. The current list is on [openrouter.ai/models](https://openrouter.ai/models).

`cwled.yaml`:

```yaml
llm:
  provider: openrouter
  LLMModel: openai/gpt-4o-mini
  base_url: null              # the OpenRouter endpoint is used by default
  temperature: 0.1
  max_tokens: 4096
  api_key_env: OPENROUTER_API_KEY
```

`cwled.env`:

```bash
OPENROUTER_API_KEY=sk-or-your-openrouter-key
```

> **Unverified:** the provider is registered in the LangChain `init_chat_model` mapping and accepts `api_key`, `base_url`, `temperature` and `max_tokens`. The end-to-end call has not been tested in this repository.

---

## 5. Using the features

1. Open the configuration dialog, choose the **AI Assistant** tab, select the provider, enter the model and (if needed) the base URL, and save the API key. Or edit `cwled.yaml` and `cwled.env` directly.
2. **Draft a tool:** *Tools → Draft CommandLineTool from documentation*, paste the help text, click **Draft tool**. The file `_draft_<tool>.cwl` is written to the current working directory.
3. **Troubleshoot:** load a CWL document, use the troubleshoot action, describe the problem, click **OK**. Save the response with **Save Response** if needed.

If a call fails, the error is written to the log (see `cwled/logger.py`) and, for missing keys and model initialization errors, shown in a message box.

---

## 6. Keeping this document current

Update this file whenever any of the following change:

- the providers offered in `ConfigDialog.py` or handled in `BaseLLM.setModel`;
- the keys read from the `llm` block, or their defaults in `resources/config/cwled.yaml`;
- the key lookup order or the `cwled.env` format;
- a system prompt, or the input sent to a model;
- how requests are made (synchronous, streaming, threading, tool use);
- the provider packages in `pyproject.toml` or `cwled.spec`.

---

## 7. Known issues

These were found by reading the code. Items 1, 3, 4, 5, 8, 9 and 10 are fixed; the others are open.

| # | Location | Problem | Effect |
|---|---|---|---|
| 1 | `cwled/ChildWindow.py` (`onMenuTroubleshoot`) | Fixed. It read `llm.get('model', ...)` and passed `gemini-2.5-flash`, ignoring `LLMModel`. | Troubleshoot now uses the provider and model from the settings, like the other features. |
| 2 | `cwled/draft.py` (`onDraftTool`) | A `ValueError` is caught and only logged, with no message to the user. The `except` block also checks `progress_msg`, which is never defined. | A failure that raises `ValueError` may appear to do nothing. |
| 3 | `cwled/LLM.py` (`DocumentationToolLLM.preparePrompt`) | Fixed. The additional documentation was inserted as `{json.dumps}` (function repr) instead of being serialized. | Workflow step documentation now reaches the model. |
| 4 | `cwled/LLM.py` (`BaseLLM.__init__`) | Fixed. The legacy model-name table (`gpt-4o-mini`, `gpt-4`, `gemini-2.5-flash`) that overrode the configured `provider` and key variable has been removed. | The provider and key variable always come from the settings. |
| 5 | `cwled/LLM.py` (`BaseLLM.invokeModel`) | Fixed. Calls ran synchronously on the GUI thread, which froze the application. | Requests run in `LLMJob` (`cwled/llm_jobs.py`); the window stays usable. |
| 6 | `cwled/ConfigDialog.py` (save) | The API key is stored in plain text in `cwled.env`. | Anyone with read access to the user configuration directory can read the key. |
| 7 | `README.md` | Says `LLModel`; the key is `LLMModel`. | Users who follow the README write a key the application ignores. |
| 8 | `pyproject.toml`, `cwled.spec` | `langchain-ollama` and `langchain-openrouter` were not in the packaging. | Fixed: both are in `pyproject.toml`, and `cwled.spec` collects them and lists them as hidden imports. |
| 9 | `cwled/LLM.py` (`DocumentationToolLLM.__init__`) | Fixed. The model defaulted to `gemini-2.5-flash`, which `BaseLLM` mapped to Google and `GOOGLE_API_KEY`, ignoring the configured `provider`, `LLMModel` and `api_key_env`. The default is now `None`. | The Info-tab AI button uses the provider and model from the settings. |
| 10 | `cwled/TabInfoWindow.py` (`onAIButtonPressed`) | Fixed. Errors were only logged. | Errors, including a missing API key or an unsupported CWL class, are shown in a message box. A missing key can show two boxes: the key message from `BaseLLM`, then the error from the Info tab. |
