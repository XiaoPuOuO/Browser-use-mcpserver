# browser-use MCP（Cursor `agent` または OpenAI 互換ローカルモデル）

**言語：** [English](../../README.md) · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md) · **日本語（このページ）**

[browser-use](https://github.com/browser-use/browser-use) でブラウザ自動化を実行します。推論用 LLM は **環境変数** で切り替えられます。

- **既定 `cursor_agent`**：ローカルの **`agent`（Cursor Agent CLI）** 子プロセス（`agent login` が必要）。
- **`openai`**：browser-use 組み込みの **OpenAI 形式** `ChatOpenAI`（`base_url` + `api_key` + `model` で LM Studio、Ollama 互換エンドポイント、vLLM などを指せます）。

## 要件

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（推奨）
- ローカルの Chromium／Chrome（browser-use は既定で Playwright でブラウザを制御）
- **`cursor_agent` を使う場合**：`agent` をインストールし、**`agent login`** 済みであること
- **`openai` を使う場合**：互換サービスを起動し、MCP の `env` に URL／モデルを設定（下記参照）

## インストール

```bash
cd /path/to/Browser-use-mcpserver
uv sync
```

### MCP に URL は必要？先にサーバーを起動？

本プロジェクトは **stdio** で Cursor と通信します：**MCP の URL は不要**で、**常駐の Web サービスも不要**です。Cursor が `command` + `args` で子プロセスを自動起動します。  
（OpenAI 互換モードの `BROWSER_USE_OPENAI_BASE_URL` は **LLM の HTTP API** のアドレスであり、MCP の転送とは無関係です。）

### 「browser-use を別途入れる？」について

- **Python パッケージ**：`uv sync` で `browser-use` が **`.venv`** に入ります。
- **ブラウザ**：実行ファイルがない場合は [browser-use の公式手順](https://github.com/browser-use/browser-use) に従ってください（例：`uvx browser-use install`）。

## LLM バックエンドの切り替え（MCP `env`）

| `BROWSER_USE_MCP_LLM` | 動作 |
|------------------------|------|
| `cursor_agent`（既定） | 子プロセスでローカル `agent` を呼ぶ（`--model` は下表、既定 **auto**） |
| `openai` | OpenAI 互換 HTTP API（公式またはローカル） |

### `cursor_agent`：`agent --model`（既定 **auto**）

| 変数 | 説明 |
|------|------|
| `BROWSER_USE_CURSOR_AGENT_MODEL` または `CURSOR_AGENT_MODEL` | `agent --model` に渡す値。未設定は **auto**。`agent --list-models` で利用可能な id を確認。**空白のみ**にすると `--model` を付けず agent 既定を使う |

なお：MCP の非対話呼び出し時、プログラムは `agent` に自動で **`--yolo`**（`--force` と同等）と **`--trust`**（`--print` 時に workspace 信頼プロンプトを省略）を付けます。MCP 設定で手動で重複指定する必要はありません。

OpenAI 互換の場合は Cursor の MCP 設定の **`env`** に記載することを推奨します（名前はどちらか一方で可。プロジェクトは `BROWSER_USE_*` を優先して読みます）。

| 変数 | 説明 |
|------|------|
| `BROWSER_USE_OPENAI_BASE_URL` または `OPENAI_BASE_URL` | API ルート。例：`http://127.0.0.1:1234/v1` |
| `BROWSER_USE_OPENAI_API_KEY` または `OPENAI_API_KEY` | キー。ローカル `base_url` のみで検証しない場合は省略可（プレースホルダを使用） |
| `BROWSER_USE_OPENAI_MODEL` または `OPENAI_MODEL` | モデル id（サービスに依存） |
| `BROWSER_USE_OPENAI_TEMPERATURE` | 任意、浮動小数点 |

テンプレートはリポジトリ内の **`.env.example`** を参照してください。

### トラブルシュート：`No module named browser_use_cursor_mcp`

Cursor が **システムの `python`**（例：`/opt/homebrew/.../python3.14`）を使っており、プロジェクトで `uv sync` した環境ではないことを示します。

1. 上記の **`uv run --project <プロジェクトの絶対パス>`** または **`scripts/run-mcp.sh`** を使い、`python3` / `python` のみを呼ばないでください。
2. `cwd` + `uv run` を使う場合、**`cwd` は `pyproject.toml` があるプロジェクトルート**である必要があります。

### トラブルシュート：`cursor_agent` が `{"type":"result","result":...}` でラップされ `AgentOutput` のパースに失敗する

Cursor の `agent --output-format json` は、モデル出力を **`result` 文字列**内に置くことが多いです（前置き + 末尾の schema 準拠 JSON）。本プロジェクトは外側を剥がし、テキストから `AgentOutput` を通過する JSON を抽出します。それでも失敗する場合は Cursor で本 repo を更新し、MCP を再読み込みしてください。

## Cursor MCP 設定例

**パスはローカル clone の絶対パスに置き換えてください。** **`uv run --project …`**（または下記スクリプト）を推奨します。Cursor の `cwd` がずれても Homebrew のシステム Python を誤って使いにくくなります。

**方法 A：`uv run --project`（推奨）**

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

**方法 A'：起動スクリプト（MCP の cwd に依存しない）**

```json
{
  "mcpServers": {
    "browser-use-cursor-agent": {
      "command": "/Users/xiaopu/MyProject/Browser-use-mcpserver/scripts/run-mcp.sh"
    }
  }
}
```

（初回は `chmod +x scripts/run-mcp.sh` を実行してください。）

**OpenAI 互換ローカルモデル（LM Studio / Ollama 互換 API など）**

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

**方法 B：Node `child_process.spawn` ブリッジ**

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

（ブリッジは環境変数を継承します。OpenAI モードにする場合は同 MCP に上記の `env` を追加してください。）

## ツール

| 名前 | 説明 |
|------|------|
| `browser_use_run_task` | 自然言語タスク。LLM バックエンドは `BROWSER_USE_MCP_LLM` で決まる |

### なぜ tool が一つだけ？

**意図的な簡素設計であり、不具合ではありません。** この MCP はブラウザ自動化全体を **`browser_use_run_task`** にまとめ、[browser-use](https://github.com/browser-use/browser-use) が内部で段階的に判断します。Cursor から一文投げて走らせる用途に向きます。  
「ナビゲート／クリック／状態取得」など細かい MCP tool が複数必要な場合は、公式パッケージ付属の MCP（`uvx browser-use --mcp` など）の形になります。本 repo は **カスタム LLM（`agent` または OpenAI 互換）** と薄い統合層に焦点を当てているため、tool 数は少なくなっています。

## その他の環境変数

| 変数 | 説明 |
|------|------|
| `BROWSER_USE_MCP_DEBUG` | 既定はオフ。`1` / `true` / `yes` / `on` で**ローカル Chromium ウィンドウを表示**（`Browser(headless=False)`）。オフはヘッドレス（`headless=True`）。**ツール引数では制御しません**（Cursor の自動引数との混乱を避けるため）。[browser-use `Browser`](https://github.com/browser-use/browser-use) のローカル利用と同様です。 |
| `BROWSER_USE_MCP_PAGE_READINESS_TIMEOUT_SEC` | **正の数**（秒）を指定すると、`NavigateToUrlEvent.timeout_ms` 未指定時の「**クロスドメイン**」CDP ページ準備待ち上限を上書き（ライブラリ既定 **8** 秒）。**同一ドメイン**は既定 **3** 秒のまま。`Page readiness timeout` が出る遅い SPA 向けに例: `20`。 |
| `CURSOR_AGENT_CMD` | `cursor_agent` モードのみ。既定 `agent` |
| `BROWSER_USE_CURSOR_AGENT_MODEL` / `CURSOR_AGENT_MODEL` | 「LLM バックエンド」節を参照。`agent --model`（既定 `auto`） |
| `BROWSER_USE_CURSOR_AGENT_RESUME` | 既定 `1`。`0` / `false` / `no` / `off` で ``--resume`` を無効化。**`BROWSER_USE_CURSOR_AGENT_TRANSPORT=sdk_stdio` では無視**（SDK が browser-use `session_id` ごとに単一プロセス内で Agent を維持）。 |
| `BROWSER_USE_CURSOR_AGENT_TRANSPORT` | 未設定：各ステップで ``agent`` CLI。**`sdk_stdio`**：単一 Node + ``@cursor/sdk``（``node/`` で ``npm install``、**`CURSOR_API_KEY`**）。モデルは原則 **`BROWSER_USE_CURSOR_AGENT_MODEL`**／**`CURSOR_AGENT_MODEL`** と同じ；**`auto`**（および空白）は SDK 向けに **`default`** にマップ（SDK は ``auto`` 文字列不可）。任意：`NODE_BIN`、`BROWSER_USE_CURSOR_AGENT_WORKSPACE`。 |
| `CURSOR_API_KEY` | **`sdk_stdio`** では**必須**。 |
| `BROWSER_USE_CURSOR_AGENT_PLAINTEXT_FALLBACK` | 既定 `1`。Cursor `agent` の `result` がプレーンテキストで、検証可能な `AgentOutput` JSON が含まれない場合、**`done` アクションにラップ**して browser-use を継続させる。`0` / `false` / `no` / `off` で**無効**（厳密な JSON のみ）。 |
| `BROWSER_USE_SETUP_LOGGING` | サーバー起動時に `false` にすると MCP stdio を汚染しにくくなる |
| `BROWSER_USE_MCP_LLM_TIMEOUT_SEC` | `Agent.llm_timeout`（秒）。既定 `600` |
| `BROWSER_USE_CURSOR_AGENT_LLM_TIMEOUT_SEC` | 上記の旧名。引き続き有効 |

## LangChain アノテーションとの差異

browser-use **0.12+** の `BaseChatModel` は **Protocol** で、**`async def ainvoke`** の実装が必要です。`cursor_agent` はカスタム `ChatCursorAgentCLI` を使い、`openai` はパッケージ組み込みの `ChatOpenAI` を使います。
