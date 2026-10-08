# browser-use MCP（可选 Cursor `agent` 或 OpenAI 兼容本地模型）

**语言：** [English](../../README.md) · [繁體中文](README.zh-TW.md) · **简体中文（本页）** · [日本語](README.ja.md)

使用 [browser-use](https://github.com/browser-use/browser-use) 执行浏览器自动化。推理用的 LLM 可通过 **环境变量** 切换：

- **默认 `cursor_agent`**：本地 **`agent`（Cursor Agent CLI）** 子进程（需 `agent login`）。
- **`openai`**：browser-use 内置的 **OpenAI 格式** `ChatOpenAI`（`base_url` + `api_key` + `model` 可指向本地 LM Studio、Ollama 兼容端点、vLLM 等）。

## 要求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（推荐）
- 本地 Chromium／Chrome（browser-use 默认使用 Playwright 控制浏览器）
- **若使用 `cursor_agent`**：已安装 `agent`，且完成 **`agent login`**
- **若使用 `openai`**：你的兼容服务已启动，并在 MCP `env` 中配置 URL／模型（见下）

## 安装

```bash
cd /path/to/Browser-use-mcpserver
uv sync
```

### MCP 要不要 URL？要不要自己先启动？

本项目使用 **stdio** 与 Cursor 通信：**不需要配置 MCP 的 URL**，也**不必**先常驻一个网站服务；Cursor 按 `command` + `args` 自动启动子进程。  
（OpenAI 兼容模式里填的 `BROWSER_USE_OPENAI_BASE_URL` 是 **LLM HTTP API** 的地址，与 MCP 传输无关。）

### 关于「要不要另外安装 browser-use？」

- **Python 包**：`uv sync` 会把 `browser-use` 装进 **`.venv`**。
- **浏览器**：若缺可执行文件，按 [browser-use 官方说明](https://github.com/browser-use/browser-use) 安装（例如 `uvx browser-use install`）。

## LLM 后端切换（MCP `env`）

| `BROWSER_USE_MCP_LLM` | 行为 |
|------------------------|------|
| `cursor_agent`（默认） | 子进程调用本地 `agent`（`--model` 见下表，默认 **auto**） |
| `openai` | OpenAI 兼容 HTTP API（官方或本地） |

### `cursor_agent`：`agent --model`（默认 **auto**）

| 变量 | 说明 |
|------|------|
| `BROWSER_USE_CURSOR_AGENT_MODEL` 或 `CURSOR_AGENT_MODEL` | 传给 `agent --model`；未设置时为 **auto**；可用 `agent --list-models` 查账号可用 id；若设为**仅空白**则不传 `--model`（使用 agent 内置默认） |

另：MCP 非交互调用时，程序会自动为 `agent` 加上 **`--yolo`**（等同 `--force`）与 **`--trust`**（配合 `--print` 时跳过 workspace 信任提示），无需在 MCP 配置里手动重复填写。

OpenAI 兼容时建议在 Cursor MCP 配置的 **`env`** 填写（名称二选一即可，项目优先读 `BROWSER_USE_*`）：

| 变量 | 说明 |
|------|------|
| `BROWSER_USE_OPENAI_BASE_URL` 或 `OPENAI_BASE_URL` | API 根，例如 `http://127.0.0.1:1234/v1` |
| `BROWSER_USE_OPENAI_API_KEY` 或 `OPENAI_API_KEY` | 密钥；若只设本地 `base_url` 且服务不校验，可不填（会用占位字符串） |
| `BROWSER_USE_OPENAI_MODEL` 或 `OPENAI_MODEL` | 模型 id（依你的服务） |
| `BROWSER_USE_OPENAI_TEMPERATURE` | 可选，浮点数 |

模板可参考项目内 **`.env.example`**。

### 故障排除：`No module named browser_use_cursor_mcp`

表示 Cursor 用了**系统的 `python`**（例如 `/opt/homebrew/.../python3.14`），而不是项目里已 `uv sync` 的环境。

1. 请改用上方 **`uv run --project <项目绝对路径>`** 或 **`scripts/run-mcp.sh`**，不要写成只调用 `python3` / `python`。
2. 若仍用 `cwd` + `uv run` 的写法，请确认 **`cwd` 必须是含有 `pyproject.toml` 的项目根目录**。

### 故障排除：`cursor_agent` 返回已包在 `{"type":"result","result":...}` 导致 AgentOutput 解析失败

Cursor `agent --output-format json` 常把模型内容放在 **`result` 字符串**里（前缀说明 + 末尾一段符合 schema 的 JSON）。本项目会自动剥除外层并从文本中提取可通过 `AgentOutput` 验证的 JSON；若仍失败，请在 Cursor 更新本仓库后重载 MCP。

## Cursor MCP 配置示例

**请将路径改为你本地 clone 的绝对路径。** 建议使用 **`uv run --project …`**（或下方脚本），即使 Cursor 没带对 `cwd`、也不会误用 Homebrew 的系统 Python。

**方式 A：`uv run --project`（推荐）**

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

**方式 A'：启动脚本（不依赖 MCP 的 cwd）**

```json
{
  "mcpServers": {
    "browser-use-cursor-agent": {
      "command": "/Users/xiaopu/MyProject/Browser-use-mcpserver/scripts/run-mcp.sh"
    }
  }
}
```

（首次请执行 `chmod +x scripts/run-mcp.sh`。）

**OpenAI 兼容本地模型（LM Studio / Ollama 兼容 API 等）**

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

**方式 B：Node `child_process.spawn` 桥接**

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

（桥接脚本会继承环境变量；若要 OpenAI 模式，请在 Cursor 对该 MCP 同样加上述 `env`。）

## 工具

| 名称 | 说明 |
|------|------|
| `browser_use_run_task` | 自然语言任务；LLM 后端由 `BROWSER_USE_MCP_LLM` 决定 |

### 为什么只有一个 tool？

**这是刻意的精简设计，并非异常。** 此 MCP 把「整段浏览器自动化」包成一个 **`browser_use_run_task`**，由 [browser-use](https://github.com/browser-use/browser-use) 内部逐步决策；适合从 Cursor 丢一句任务就跑完。  
若你需要「导航／点击／取状态」等多个细粒度 MCP tool，那是官方包内置 MCP（`uvx browser-use --mcp` 那类）的产品形态；本仓库专注在 **自定义 LLM（`agent` 或 OpenAI 兼容）** 与较薄的集成层，因此 tool 数量少。

## 其他环境变量

| 变量 | 说明 |
|------|------|
| `BROWSER_USE_MCP_DEBUG` | 默认关闭。设为 `1` / `true` / `yes` / `on` 时**显示本地 Chromium 窗口**（`Browser(headless=False)`）；关闭时为无头（`headless=True`）。**不由工具参数控制**，避免 Cursor 自动带参造成混淆。与 [browser-use `Browser`](https://github.com/browser-use/browser-use) 本地用法一致。 |
| `BROWSER_USE_MCP_PAGE_READINESS_TIMEOUT_SEC` | 若设为**正数**（秒），覆盖 browser-use 在「**跨域**」导航且未指定 `timeout_ms` 时 CDP 页面就绪轮询上限（库默认 **8** 秒）；**同域**仍为内置 **3** 秒。慢站／SPA 出现 `Page readiness timeout` 时可酌情调大（如 `20`）。 |
| `CURSOR_AGENT_CMD` | 仅 `cursor_agent` 模式；默认 `agent` |
| `BROWSER_USE_CURSOR_AGENT_MODEL` / `CURSOR_AGENT_MODEL` | 见「LLM 后端」一节；`agent --model`（默认 `auto`） |
| `BROWSER_USE_CURSOR_AGENT_RESUME` | 默认 `1`。设为 `0` / `false` / `no` / `off` 则关闭 ``--resume``。**`BROWSER_USE_CURSOR_AGENT_TRANSPORT=sdk_stdio` 时不适用**（由 SDK 在单进程内按 browser-use `session_id` 维持 Agent）。 |
| `BROWSER_USE_CURSOR_AGENT_TRANSPORT` | 未设置时：每步 ``agent`` CLI 子进程。**`sdk_stdio`**：单 Node 常驻 + ``@cursor/sdk``（``node/`` 需 ``npm install``、**`CURSOR_API_KEY`**）。模型一般同 **`BROWSER_USE_CURSOR_AGENT_MODEL`**／**`CURSOR_AGENT_MODEL`**；**`auto`**（及空白）映射为 SDK 的 **`default`**。可选：`NODE_BIN`、`BROWSER_USE_CURSOR_AGENT_WORKSPACE`。 |
| `CURSOR_API_KEY` | **`sdk_stdio`** 时必填。 |
| `BROWSER_USE_CURSOR_AGENT_PLAINTEXT_FALLBACK` | 默认 `1`。当 Cursor `agent` 的 `result` 为纯文本、正文无可验证的 `AgentOutput` JSON 时，**自动包装为 `done` 动作**以便 browser-use 继续。设为 `0` / `false` / `no` / `off` 则**关闭**（仅接受严格 JSON）。 |
| `BROWSER_USE_SETUP_LOGGING` | 服务器启动时设为 `false` 以免污染 MCP stdio |
| `BROWSER_USE_MCP_LLM_TIMEOUT_SEC` | `Agent.llm_timeout`（秒），默认 `600` |
| `BROWSER_USE_CURSOR_AGENT_LLM_TIMEOUT_SEC` | 同上之旧名称，仍有效 |

## 与 LangChain 注解的差异

browser-use **0.12+** 的 `BaseChatModel` 为 **Protocol**，需实现 **`async def ainvoke`**。`cursor_agent` 使用自定义 `ChatCursorAgentCLI`；`openai` 使用包内置 `ChatOpenAI`。
