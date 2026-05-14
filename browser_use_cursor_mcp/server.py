"""精簡 MCP：單一工具以 browser-use + Cursor `agent` CLI 執行任務。"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions


def _env_truthy(key: str) -> bool:
	"""辨識常見的「開／關」字串（大小寫不敏感）。"""
	return os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on")


def _clamp_int(value: int, lo: int, hi: int) -> int:
	return max(lo, min(value, hi))


_browser_session_navigate_patched = False


def _apply_browser_session_page_readiness_timeout_from_env() -> None:
	"""
	browser-use 在 ``NavigateToUrlEvent.timeout_ms`` 未設定時，跨網域預設只輪詢 **8s** CDP lifecycle
	（見 ``BrowserSession._navigate_and_wait``）。慢站會出現 ``Page readiness timeout`` 警告。

	若設定 **BROWSER_USE_MCP_PAGE_READINESS_TIMEOUT_SEC**（正數，秒），則覆寫「跨網域」該段等待上限；
	同網域仍維持函式庫預設 **3s**。
	"""
	global _browser_session_navigate_patched
	if _browser_session_navigate_patched:
		return
	raw = (os.environ.get("BROWSER_USE_MCP_PAGE_READINESS_TIMEOUT_SEC") or "").strip()
	if not raw:
		return
	try:
		cross_domain_sec = float(raw)
	except ValueError:
		return
	if cross_domain_sec <= 0:
		return

	from browser_use.browser.session import BrowserSession

	orig = BrowserSession._navigate_and_wait

	async def _navigate_and_wait_with_env_cross_domain_timeout(  # type: ignore[no-untyped-def]
		self,
		url: str,
		target_id: str,
		timeout: float | None = None,
		wait_until: str = "load",
		nav_timeout: float | None = None,
	):
		if timeout is None:
			target = self.session_manager.get_target(target_id)
			current_url = target.url
			same_domain = (
				url.split("/")[2] == current_url.split("/")[2]
				if url.startswith("http") and current_url.startswith("http")
				else False
			)
			timeout = 3.0 if same_domain else cross_domain_sec
		return await orig(self, url, target_id, timeout=timeout, wait_until=wait_until, nav_timeout=nav_timeout)

	BrowserSession._navigate_and_wait = _navigate_and_wait_with_env_cross_domain_timeout  # type: ignore[method-assign]
	_browser_session_navigate_patched = True


def _resolve_step_timeout_sec(arguments: dict[str, Any]) -> int:
	"""
	單步逾時（browser-use ``Agent.step_timeout``）。預設 600 秒，因 ``cursor_agent`` 每步需子行程
	呼叫 ``agent``，且含截圖時常超過函式庫預設的 180 秒。
	"""
	if arguments.get("step_timeout") is not None:
		return _clamp_int(int(arguments["step_timeout"]), 30, 7200)
	env_v = (os.environ.get("BROWSER_USE_MCP_STEP_TIMEOUT_SEC") or "").strip()
	if env_v:
		return _clamp_int(int(env_v), 30, 7200)
	return 600


def _tool_run_task_schema() -> dict[str, Any]:
	return {
		"type": "object",
		"properties": {
			"task": {
				"type": "string",
				"description": "要以瀏覽器完成的任務（自然語言），例如「開啟 https://example.com 並回傳標題」",
				"minLength": 1,
			},
			"max_steps": {
				"type": "integer",
				"description": "最多允許的代理步數",
				"default": 75,
				"minimum": 1,
				"maximum": 500,
			},
			"step_timeout": {
				"type": "integer",
				"description": (
					"單一步驟逾時秒數（含 LLM 與瀏覽器操作）。"
					"未指定時使用 MCP 環境變數 BROWSER_USE_MCP_STEP_TIMEOUT_SEC，仍無則預設 600（高於 browser-use 內建 180，適合 cursor_agent + 截圖）。"
				),
				"minimum": 30,
				"maximum": 7200,
			},
		},
		"required": ["task"],
	}


async def _handle_browser_use_run_task(arguments: dict[str, Any]) -> list[types.Content]:
	"""延遲 import 重型依賴，僅在呼叫工具時載入。"""
	from browser_use import Agent, Browser

	from browser_use_cursor_mcp.llm.resolve import resolve_llm_from_env

	_apply_browser_session_page_readiness_timeout_from_env()

	task = str(arguments["task"]).strip()
	if not task:
		raise ValueError("task 不可為空")

	max_steps = int(arguments.get("max_steps", 75))
	# 是否顯示瀏覽器視窗**僅**由 MCP 環境變數 BROWSER_USE_MCP_DEBUG 決定（不開放工具參數，避免與 Cursor 自動帶參混淆）
	debug_visible = _env_truthy("BROWSER_USE_MCP_DEBUG")
	headless = not debug_visible

	llm = resolve_llm_from_env()
	browser = Browser(headless=headless)
	llm_timeout = int(
		os.environ.get("BROWSER_USE_MCP_LLM_TIMEOUT_SEC")
		or os.environ.get("BROWSER_USE_CURSOR_AGENT_LLM_TIMEOUT_SEC", "600")
	)
	step_timeout = _resolve_step_timeout_sec(arguments)
	agent = Agent(
		task=task,
		llm=llm,
		browser=browser,
		enable_signal_handler=False,
		llm_timeout=llm_timeout,
		step_timeout=step_timeout,
	)

	history = await agent.run(max_steps=max_steps)

	final = history.final_result()
	success = history.is_successful()
	err_list = [e for e in history.errors() if e]

	summary: dict[str, Any] = {
		"final_result": final,
		"is_successful": success,
		"is_done": history.is_done(),
		"errors": err_list,
		"last_action": history.last_action(),
		"browser_headless": headless,
		"mcp_debug_visible": debug_visible,
		"step_timeout_sec": step_timeout,
		"llm_timeout_sec": llm_timeout,
	}

	return [types.TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]


def build_server() -> Server:
	srv = Server("browser-use-cursor-agent")

	@srv.list_tools()
	async def _list_tools() -> list[types.Tool]:
		return [
			types.Tool(
				name="browser_use_run_task",
				description=(
					"本機 browser-use：以自然語言執行瀏覽器任務。"
					"LLM 與是否顯示 Chromium 視窗僅能透過 MCP 的 env 設定（見專案 README：BROWSER_USE_MCP_LLM、BROWSER_USE_MCP_DEBUG）。"
				),
				inputSchema=_tool_run_task_schema(),
			),
		]

	@srv.call_tool()
	async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.Content]:
		args = arguments or {}
		if name == "browser_use_run_task":
			return await _handle_browser_use_run_task(args)
		raise ValueError(f"未知工具: {name}")

	return srv


async def run_stdio_server() -> None:
	server = build_server()
	async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
		await server.run(
			read_stream,
			write_stream,
			InitializationOptions(
				server_name="browser-use-cursor-agent",
				server_version="0.1.0",
				capabilities=server.get_capabilities(
					notification_options=NotificationOptions(),
					experimental_capabilities={},
				),
			),
		)


def main() -> None:
	asyncio.run(run_stdio_server())


if __name__ == "__main__":
	main()
