# browser-use MCP (optional Cursor `agent` or OpenAI-compatible local models)

**Languages:** English (this page) · [繁體中文](documents/MultiLanguage/README.zh-TW.md) · [简体中文](documents/MultiLanguage/README.zh-CN.md) · [日本語](documents/MultiLanguage/README.ja.md)

Runs browser automation with [browser-use](https://github.com/browser-use/browser-use). The LLM used for reasoning is selected via **environment variables**:

- **Default `cursor_agent`**: by default, each step spawns the local **`agent` (Cursor Agent CLI)** subprocess (requires `agent login`). Set **`BROWSER_USE_CURSOR_AGENT_TRANSPORT=sdk_stdio`** to use **one long-lived Node process** with **`@cursor/sdk`** (`Agent.send` per step; requires **`CURSOR_API_KEY`** from Dashboard → Integrations and `npm install` in `node/`).
- **`openai`**: browser-use’s built-in **OpenAI-style** `ChatOpenAI` (`base_url` + `api_key` + `model` can point at LM Studio, Ollama-compatible endpoints, vLLM, etc.).

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended)
- Local Chromium/Chrome (browser-use drives the browser with Playwright by default)
- **For `cursor_agent`**: `agent` installed and **`agent login`** completed (CLI mode). For **`sdk_stdio`**: run **`npm install`** in **`node/`** and set **`CURSOR_API_KEY`** (Dashboard → Integrations; not the same as `agent login`).
- **For `openai`**: your compatible service is running and URL/model are set in the MCP `env` (below)

## Install

```bash
cd /path/to/Browser-use-mcpserver
uv sync
```

### Does the MCP need a URL? Do I start a server first?

This project talks to Cursor over **stdio**: **no MCP URL** is required, and you **do not** need to keep a separate web service running; Cursor starts the subprocess from `command` + `args`.  
(In OpenAI-compatible mode, `BROWSER_USE_OPENAI_BASE_URL` is the **LLM HTTP API** address; it is unrelated to MCP transport.)

### Do I install browser-use separately?

- **Python package**: `uv sync` installs `browser-use` into **`.venv`**.
- **Browser**: if the binary is missing, follow [browser-use’s official instructions](https://github.com/browser-use/browser-use) (e.g. `uvx browser-use install`).

## Switching the LLM backend (MCP `env`)

| `BROWSER_USE_MCP_LLM` | Behavior |
|------------------------|----------|
| `cursor_agent` (default) | By default: subprocess per step → local `agent` CLI (`--model` in table below, default **auto**). Optional: set **`BROWSER_USE_CURSOR_AGENT_TRANSPORT=sdk_stdio`** for one Node worker + `@cursor/sdk` (see env table). |
| `openai` | OpenAI-compatible HTTP API (hosted or local) |

### `cursor_agent`: `agent --model` (default **auto**)

| Variable | Description |
|----------|-------------|
| `BROWSER_USE_CURSOR_AGENT_MODEL` or `CURSOR_AGENT_MODEL` | Passed to `agent --model`; unset means **auto**; use `agent --list-models` for ids; set to **whitespace only** to omit `--model` (agent’s built-in default) |

For non-interactive MCP calls, the server automatically adds **`--yolo`** (same as `--force`) and **`--trust`** (with `--print`, skips workspace trust prompts) when using the **default CLI** transport; you do not need to duplicate these in MCP config. The **`sdk_stdio`** transport does not spawn the `agent` binary.

### `cursor_agent` + `sdk_stdio` (single Node worker)

1. `cd node && npm install`
2. Set **`CURSOR_API_KEY`** in MCP `env` (Dashboard → Integrations).
3. Set **`BROWSER_USE_CURSOR_AGENT_TRANSPORT=sdk_stdio`**.

Optional: **`NODE_BIN`**, **`BROWSER_USE_CURSOR_AGENT_WORKSPACE`** (SDK `cwd`). **Note:** `@cursor/sdk` does not accept the literal model id `auto`; in **`sdk_stdio`** mode, **`auto`** (and whitespace-only model) is mapped to **`default`** so it matches the SDK’s allowed list. Other ids pass through unchanged.

For OpenAI-compatible backends, set these in the MCP **`env`** in Cursor (either name works; this project prefers `BROWSER_USE_*`):

| Variable | Description |
|----------|-------------|
| `BROWSER_USE_OPENAI_BASE_URL` or `OPENAI_BASE_URL` | API root, e.g. `http://127.0.0.1:1234/v1` |
| `BROWSER_USE_OPENAI_API_KEY` or `OPENAI_API_KEY` | API key; if only a local `base_url` is set and the server does not validate keys, you may omit (a placeholder is used) |
| `BROWSER_USE_OPENAI_MODEL` or `OPENAI_MODEL` | Model id (depends on your stack) |
| `BROWSER_USE_OPENAI_TEMPERATURE` | Optional float |

See **`.env.example`** in the repo for a template.

### Troubleshooting: `No module named browser_use_cursor_mcp`

Cursor is using **system `python`** (e.g. `/opt/homebrew/.../python3.14`) instead of the project environment where `uv sync` ran.

1. Use **`uv run --project <absolute project path>`** or **`scripts/run-mcp.sh`** above; do not invoke bare `python3` / `python`.
2. If you rely on `cwd` + `uv run`, ensure **`cwd` is the project root that contains `pyproject.toml`**.

### Troubleshooting: `cursor_agent` wraps output in `{"type":"result","result":...}` and `AgentOutput` parsing fails

With `agent --output-format json`, Cursor often puts model output inside the **`result` string** (preamble + trailing JSON that matches the schema). This repo strips the outer wrapper and extracts JSON that passes `AgentOutput` validation; if it still fails, update this repo in Cursor and reload the MCP.

### Troubleshooting: `Step N timed out after 180 seconds`

That is browser-use’s **`Agent.step_timeout`** (default **180s** per step). With **`cursor_agent`** in **CLI** mode, each step waits on the local `agent` subprocess and vision-heavy prompts (e.g. screenshots) can exceed 180s. This MCP sets **`step_timeout` to 600s** when neither **`BROWSER_USE_MCP_STEP_TIMEOUT_SEC`** nor the tool argument **`step_timeout`** is set. Raise them (e.g. `900` or `1200`) for very slow runs. With **`sdk_stdio`**, each step still has the same cap, but there is no per-step `agent` process spawn.

## Example Cursor MCP configuration

**Replace paths with your local clone’s absolute path.** Prefer **`uv run --project …`** (or the script below) so Cursor’s `cwd` cannot accidentally pick Homebrew’s system Python.

**Option A: `uv run --project` (recommended)**

```json
{
  "mcpServers": {
    "browser-use-cursor-agent": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/Users/xiaopu/MyProject/Browser-use-mcpserver",
        "python",
        "-m",
        "browser_use_cursor_mcp"
      ]
    }
  }
}
```

**Option A': launch script (does not depend on MCP `cwd`)**

```json
{
  "mcpServers": {
    "browser-use-cursor-agent": {
      "command": "/Users/xiaopu/MyProject/Browser-use-mcpserver/scripts/run-mcp.sh"
    }
  }
}
```

(Run `chmod +x scripts/run-mcp.sh` once.)

**OpenAI-compatible local models (LM Studio / Ollama-compatible API, etc.)**

```json
{
  "mcpServers": {
    "browser-use-openai-local": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/Users/xiaopu/MyProject/Browser-use-mcpserver",
        "python",
        "-m",
        "browser_use_cursor_mcp"
      ],
      "env": {
        "BROWSER_USE_MCP_LLM": "openai",
        "BROWSER_USE_OPENAI_BASE_URL": "http://127.0.0.1:1234/v1",
        "BROWSER_USE_OPENAI_API_KEY": "local",
        "BROWSER_USE_OPENAI_MODEL": "your-model-name"
      }
    }
  }
}
```

**Option B: Node `child_process.spawn` bridge**

```json
{
  "mcpServers": {
    "browser-use-cursor-agent": {
      "command": "node",
      "args": ["/Users/xiaopu/MyProject/Browser-use-mcpserver/node/mcp-stdio-bridge.mjs"]
    }
  }
}
```

(The bridge inherits environment variables; for OpenAI mode, add the same `env` block to that MCP entry in Cursor.)

## Tools

| Name | Description |
|------|-------------|
| `browser_use_run_task` | Natural-language task; LLM from `BROWSER_USE_MCP_LLM`. Optional `step_timeout` (seconds per step) overrides `BROWSER_USE_MCP_STEP_TIMEOUT_SEC`; see env table. |

### Why only one tool?

**This is intentional minimalism, not a bug.** The MCP wraps a full browser automation run in **`browser_use_run_task`**; [browser-use](https://github.com/browser-use/browser-use) plans steps internally—handy for “one sentence from Cursor, run to completion.”  
If you need many fine-grained tools (navigate/click/read state), that matches the official package’s built-in MCP shape (`uvx browser-use --mcp`, etc.); this repo focuses on **custom LLMs (`agent` or OpenAI-compatible)** and a thin integration layer, hence fewer tools.

## Other environment variables

| Variable | Description |
|----------|-------------|
| `BROWSER_USE_MCP_DEBUG` | Off by default. Set to `1` / `true` / `yes` / `on` to **show the local Chromium window** (`Browser(headless=False)`); otherwise headless (`headless=True`). **Not controlled by tool arguments** to avoid confusion when Cursor injects parameters. Same idea as local [browser-use `Browser`](https://github.com/browser-use/browser-use). |
| `BROWSER_USE_MCP_PAGE_READINESS_TIMEOUT_SEC` | If set to a **positive number** (seconds), overrides browser-use’s **cross-domain** CDP “page readiness” poll cap when `NavigateToUrlEvent.timeout_ms` is unset (library default **8**). **Same-domain** navigations keep the library default **3**. Use for slow SPAs when you see `Page readiness timeout … for <url>`. |
| `CURSOR_AGENT_CMD` | `cursor_agent` mode only; default `agent` |
| `BROWSER_USE_CURSOR_AGENT_MODEL` / `CURSOR_AGENT_MODEL` | See “LLM backend”; `agent --model` (default `auto`) |
| `BROWSER_USE_CURSOR_AGENT_RESUME` | Default `1`. Set to `0` / `false` / `no` / `off` to **disable** reusing Cursor `agent --resume <session_id>` across browser-use steps (same `session_id` in kwargs). **Ignored** when `BROWSER_USE_CURSOR_AGENT_TRANSPORT=sdk_stdio` (SDK keeps one agent per `session_id` in-process). |
| `BROWSER_USE_CURSOR_AGENT_TRANSPORT` | Default unset (CLI subprocess per step). Set to **`sdk_stdio`** for a **single long-lived Node worker** using `@cursor/sdk` (`Agent.send` per step, one OS process). Requires `npm install` in `node/` and **`CURSOR_API_KEY`** (Dashboard → Integrations). Model id follows **`BROWSER_USE_CURSOR_AGENT_MODEL` / `CURSOR_AGENT_MODEL`**, except **`auto`** (and whitespace-only) maps to **`default`** for the SDK. Optional: `NODE_BIN`, `BROWSER_USE_CURSOR_AGENT_WORKSPACE` (cwd for the SDK agent). |
| `CURSOR_API_KEY` | Required for **`sdk_stdio`** transport. Not the same as interactive `agent login`. |
| `BROWSER_USE_CURSOR_AGENT_PLAINTEXT_FALLBACK` | Default `1`. When the Cursor `agent` `result` is plain text without embeddable `AgentOutput` JSON, **wrap it as a `done` action** so browser-use can continue. Set to `0` / `false` / `no` / `off` to **disable** (strict parse only). |
| `BROWSER_USE_SETUP_LOGGING` | Set to `false` on server start to avoid polluting MCP stdio |
| `BROWSER_USE_MCP_LLM_TIMEOUT_SEC` | `Agent.llm_timeout` in seconds; default `600` |
| `BROWSER_USE_MCP_STEP_TIMEOUT_SEC` | **`Agent.step_timeout`** (per-step cap, seconds). browser-use defaults to **180**; with **`cursor_agent`** each step runs the local `agent` subprocess and screenshots are heavy, so this MCP uses **600** when unset. Override per call with tool arg `step_timeout` (30–7200). |
| `BROWSER_USE_CURSOR_AGENT_LLM_TIMEOUT_SEC` | Legacy alias for LLM timeout; still honored |

## Difference from LangChain annotations

In browser-use **0.12+**, `BaseChatModel` is a **Protocol** requiring **`async def ainvoke`**. `cursor_agent` uses custom `ChatCursorAgentCLI`; `openai` uses the package’s `ChatOpenAI`.
