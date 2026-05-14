#!/usr/bin/env bash
# 給 Cursor MCP 用：不依賴 MCP 設定的 cwd，一律以專案根目錄執行 uv。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run --project "$ROOT" python -m browser_use_cursor_mcp
