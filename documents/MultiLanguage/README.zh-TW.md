# browser-use MCP（可選 Cursor `agent` 或 OpenAI 相容本機模型）

**語言：** [English](../../README.md) · **繁體中文（本頁）** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

以 [browser-use](https://github.com/browser-use/browser-use) 執行瀏覽器自動化。推理用的 LLM 可由 **環境變數**切換：

- **預設 `cursor_agent`**：本機 **`agent`（Cursor Agent CLI）** 子行程（需 `agent login`）。
- **`openai`**：browser-use 內建的 **OpenAI 格式** `ChatOpenAI`（`base_url` + `api_key` + `model` 可指向本機 LM Studio、Ollama 相容端點、vLLM 等）。

## 需求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（建議）
- 本機 Chromium／Chrome（browser-use 預設使用 Playwright 控制瀏覽器）
- **若使用 `cursor_agent`**：已安裝 `agent`，且完成 **`agent login`**
- **若使用 `openai`**：你的相容服務已啟動，並在 MCP `env` 中設定 URL／模型（見下）

## 安裝

```bash
cd /path/to/Browser-use-mcpserver
uv sync
```

### MCP 要不要網址？要不要自己先啟動？

本專案使用 **stdio** 與 Cursor 通訊：**不需要設定 MCP 的 URL**，也**不必**先手動常駐一個網站服務；Cursor 依 `command` + `args` 自動啟動子行程。  
（OpenAI 相容模式裡填的 `BROWSER_USE_OPENAI_BASE_URL` 是 **LLM HTTP API** 的位址，與 MCP 傳輸無關。）

### 關於「要不要另外安裝 browser-use？」

- **Python 套件**：`uv sync` 會把 `browser-use` 裝進 **`.venv`**。
- **瀏覽器**：若缺執行檔，依 [browser-use 官方說明](https://github.com/browser-use/browser-use) 安裝（例如 `uvx browser-use install`）。

## LLM 後端切換（MCP `env`）

| `BROWSER_USE_MCP_LLM` | 行為 |
|------------------------|------|
| `cursor_agent`（預設） | 子行程呼叫本機 `agent`（`--model` 見下表，預設 **auto**） |
| `openai` | OpenAI 相容 HTTP API（官方或本機） |

### `cursor_agent`：`agent --model`（預設 **auto**）

| 變數 | 說明 |
|------|------|
| `BROWSER_USE_CURSOR_AGENT_MODEL` 或 `CURSOR_AGENT_MODEL` | 傳給 `agent --model`；未設定時為 **auto**；可用 `agent --list-models` 查帳號可用 id；若設為**僅空白**則不傳 `--model`（使用 agent 內建預設） |

另：MCP 非互動呼叫時，程式會自動為 `agent` 加上 **`--yolo`**（等同 `--force`）與 **`--trust`**（搭配 `--print` 時略過 workspace 信任提示），無需在 MCP 設定裡手動重複填寫。

OpenAI 相容時建議在 Cursor MCP 設定的 **`env`** 填寫（名稱擇一即可，專案優先讀 `BROWSER_USE_*`）：

| 變數 | 說明 |
|------|------|
| `BROWSER_USE_OPENAI_BASE_URL` 或 `OPENAI_BASE_URL` | API 根，例如 `http://127.0.0.1:1234/v1` |
| `BROWSER_USE_OPENAI_API_KEY` 或 `OPENAI_API_KEY` | 金鑰；若只設本機 `base_url` 且服務不驗證，可不填（會用佔位字串） |
| `BROWSER_USE_OPENAI_MODEL` 或 `OPENAI_MODEL` | 模型 id（依你的服務） |
| `BROWSER_USE_OPENAI_TEMPERATURE` | 可選，浮點數 |

範本可參考專案內 **`.env.example`**。

### 故障排除：`No module named browser_use_cursor_mcp`

代表 Cursor 用了**系統的 `python`**（例如 `/opt/homebrew/.../python3.14`），而不是專案裡已 `uv sync` 的環境。

1. 請改用上方 **`uv run --project <專案絕對路徑>`** 或 **`scripts/run-mcp.sh`**，不要寫成只呼叫 `python3` / `python`。
2. 若仍用 `cwd` + `uv run` 的寫法，請確認 **`cwd` 必須是含有 `pyproject.toml` 的專案根目錄**。

### 故障排除：`cursor_agent` 回傳已包在 `{"type":"result","result":...}` 導致 AgentOutput 解析失敗

Cursor `agent --output-format json` 常把模型內容放在 **`result` 字串**裡（前綴說明 + 末尾一段符合 schema 的 JSON）。本專案會自動剥除外層並從文字中擷取可通過 `AgentOutput` 驗證的 JSON；若仍失敗，請在 Cursor 更新本 repo 後重載 MCP。

## Cursor MCP 設定範例

**請將路徑改成你本機 clone 的絕對路徑。** 建議使用 **`uv run --project …`**（或下方腳本），即使 Cursor 沒帶對 `cwd`、也不會誤用 Homebrew 的系統 Python。

**方式 A：`uv run --project`（建議）**

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

**方式 A'：啟動腳本（不依賴 MCP 的 cwd）**

```json
{
  "mcpServers": {
    "browser-use-cursor-agent": {
      "command": "/Users/xiaopu/MyProject/Browser-use-mcpserver/scripts/run-mcp.sh"
    }
  }
}
```

（首次請執行 `chmod +x scripts/run-mcp.sh`。）

**OpenAI 相容本機模型（LM Studio / Ollama 相容 API 等）**

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

**方式 B：Node `child_process.spawn` 橋接**

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

（橋接腳本會繼承環境變數；若要 OpenAI 模式，請在 Cursor 對該 MCP 同樣加上述 `env`。）

## 工具

| 名稱 | 說明 |
|------|------|
| `browser_use_run_task` | 自然語言任務；LLM 後端由 `BROWSER_USE_MCP_LLM` 決定 |

### 為什麼只有一個 tool？

**這是刻意的精簡設計，並非異常。** 此 MCP 把「整段瀏覽器自動化」包成一個 **`browser_use_run_task`**，由 [browser-use](https://github.com/browser-use/browser-use) 內部逐步決策；適合從 Cursor 丟一句任務就跑完。  
若你需要「導航／點擊／取狀態」等多個細粒度 MCP tool，那是官方套件內建 MCP（`uvx browser-use --mcp` 那類）的產品形態；本 repo 專注在 **自訂 LLM（`agent` 或 OpenAI 相容）** 與較薄的整合層，因此 tool 數量少。

## 其他環境變數

| 變數 | 說明 |
|------|------|
| `BROWSER_USE_MCP_DEBUG` | 預設關閉。設為 `1` / `true` / `yes` / `on` 時**顯示本機 Chromium 視窗**（`Browser(headless=False)`）；關閉時為無頭（`headless=True`）。**不由工具參數控制**，避免 Cursor 自動帶參造成混淆。與 [browser-use `Browser`](https://github.com/browser-use/browser-use) 本機用法一致。 |
| `BROWSER_USE_MCP_PAGE_READINESS_TIMEOUT_SEC` | 若設為**正數**（秒），覆寫 browser-use 內「**跨網域**」導航時 CDP 頁面就緒輪詢上限（函式庫在未指定 `timeout_ms` 時預設 **8** 秒）；**同網域**仍維持內建 **3** 秒。慢載入／SPA 若出現 `Page readiness timeout` 警告可酌調大（例如 `20`）。 |
| `CURSOR_AGENT_CMD` | 僅 `cursor_agent` 模式；預設 `agent` |
| `BROWSER_USE_CURSOR_AGENT_MODEL` / `CURSOR_AGENT_MODEL` | 見「LLM 後端」一節；`agent --model`（預設 `auto`） |
| `BROWSER_USE_CURSOR_AGENT_PLAINTEXT_FALLBACK` | 預設 `1`。當 Cursor `agent` 的 `result` 為純文字、內文無可驗證的 `AgentOutput` JSON 時，**自動包成 `done` 動作**讓 browser-use 能繼續。設為 `0` / `false` / `no` / `off` 則**關閉**（僅接受嚴格 JSON）。 |
| `BROWSER_USE_SETUP_LOGGING` | 伺服器啟動時設為 `false` 以免汙染 MCP stdio |
| `BROWSER_USE_MCP_LLM_TIMEOUT_SEC` | `Agent.llm_timeout`（秒），預設 `600` |
| `BROWSER_USE_CURSOR_AGENT_LLM_TIMEOUT_SEC` | 同上之舊名稱，仍有效 |

## 與 LangChain 註解的差異

browser-use **0.12+** 的 `BaseChatModel` 為 **Protocol**，需實作 **`async def ainvoke`**。`cursor_agent` 使用自訂 `ChatCursorAgentCLI`；`openai` 使用套件內建 `ChatOpenAI`。
