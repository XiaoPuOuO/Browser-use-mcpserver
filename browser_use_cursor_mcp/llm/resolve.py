"""
依環境變數決定 browser-use 使用的 LLM：本機 `agent` CLI 或 OpenAI 相容 HTTP API（可接本機模型）。
"""

from __future__ import annotations

import os

from browser_use.llm.base import BaseChatModel


def resolve_llm_from_env() -> BaseChatModel:
	"""
	讀取 BROWSER_USE_MCP_LLM：

	- ``cursor_agent``（預設）：``ChatCursorAgentCLI`` → 預設每步以子行程呼叫本機 ``agent``（``--model`` 由
	  ``BROWSER_USE_CURSOR_AGENT_MODEL`` / ``CURSOR_AGENT_MODEL`` 決定，預設 ``auto``）。
	  若設定 **``BROWSER_USE_CURSOR_AGENT_TRANSPORT=sdk_stdio``**，改為**單一**長駐 Node worker +
	  ``@cursor/sdk``（需 ``npm install`` 於 ``node/`` 與 ``CURSOR_API_KEY``），同一 browser-use
	  ``session_id`` 內連續 ``send``，不再每步 ``exec`` ``agent``；**``auto``**（及空白模型）在 SDK 會對應為 **``default``**（@cursor/sdk 不接受字面值 ``auto``），其餘 id 與 CLI 相同。
	  同一 ``session_id`` 下 CLI 模式會記住 Cursor 回傳的 ``session_id`` 並以 ``--resume`` 重用（可用
	  ``BROWSER_USE_CURSOR_AGENT_RESUME=0`` 關閉；**sdk_stdio 模式不使用 resume**）。
	- ``openai``：``browser_use.llm.openai.chat.ChatOpenAI`` → OpenAI 官方或相容服務
	  （LM Studio、Ollama 的 OpenAI 相容端點、vLLM 等），格式與 OpenAI Chat Completions 一致。

	OpenAI 相容模式下的常用變數（可在 Cursor MCP 設定的 ``env`` 裡填）：

	- ``BROWSER_USE_OPENAI_BASE_URL`` 或 ``OPENAI_BASE_URL``：API 根位址，例如 ``http://127.0.0.1:1234/v1``。
	- ``BROWSER_USE_OPENAI_API_KEY`` 或 ``OPENAI_API_KEY``：金鑰；若已設定 ``base_url`` 且本機服務不校驗金鑰，可省略（會使用佔位字串）。
	- ``BROWSER_USE_OPENAI_MODEL`` 或 ``OPENAI_MODEL``：模型名稱（依你的本機服務而定）。
	- ``BROWSER_USE_OPENAI_TEMPERATURE``：可選，浮點數。
	"""
	raw = os.environ.get("BROWSER_USE_MCP_LLM", "cursor_agent").strip().lower().replace("-", "_")
	aliases = {"agent": "cursor_agent", "cursor": "cursor_agent", "openai_compatible": "openai", "openai_compat": "openai"}
	mode = aliases.get(raw, raw)

	if mode == "cursor_agent":
		from browser_use_cursor_mcp.llm.chat_cursor_agent_cli import ChatCursorAgentCLI

		return ChatCursorAgentCLI()

	if mode == "openai":
		return _build_chat_openai_compatible()

	raise ValueError(
		f"不支援的 BROWSER_USE_MCP_LLM={raw!r}（正規化後 {mode!r}）。"
		"請使用 cursor_agent（預設）或 openai。"
	)


def _build_chat_openai_compatible() -> BaseChatModel:
	from browser_use.llm.openai.chat import ChatOpenAI

	model = (
		os.environ.get("BROWSER_USE_OPENAI_MODEL", "").strip()
		or os.environ.get("OPENAI_MODEL", "").strip()
		or "gpt-4o-mini"
	)
	api_key = (os.environ.get("BROWSER_USE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
	base = (os.environ.get("BROWSER_USE_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").strip() or None

	if not api_key:
		if base:
			# 多數本機 OpenAI 相容服務不驗證或接受任意字串
			api_key = "not-needed"
		else:
			raise ValueError(
				"BROWSER_USE_MCP_LLM=openai 時請擇一："
				"(1) 設定 BROWSER_USE_OPENAI_BASE_URL（或 OPENAI_BASE_URL）以使用本機 OpenAI 相容 API（可不填 Key）；"
				"(2) 或設定 BROWSER_USE_OPENAI_API_KEY（或 OPENAI_API_KEY）以呼叫官方 OpenAI。"
			)

	params: dict = {"model": model, "api_key": api_key}
	if base:
		params["base_url"] = base

	temp_raw = (os.environ.get("BROWSER_USE_OPENAI_TEMPERATURE") or "").strip()
	if temp_raw:
		params["temperature"] = float(temp_raw)

	return ChatOpenAI(**params)
