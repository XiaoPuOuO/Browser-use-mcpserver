"""
長駐 **單一** Node 子程序，透過 @cursor/sdk 在同一 Agent 上連續 ``send``，
避免每個 browser-use 步驟都 ``exec`` 一次 ``agent`` CLI。

啟用：環境變數 ``BROWSER_USE_CURSOR_AGENT_TRANSPORT=sdk_stdio``（見 ``resolve_llm_from_env``）。

需求：

- 已執行 ``npm install`` 於專案 ``node/`` 目錄（含 ``@cursor/sdk``）。
- ``CURSOR_API_KEY``（Cursor Dashboard → Integrations），與 CLI ``agent login`` 不同。
- 模型 id 與 CLI 相同，由 ``BROWSER_USE_CURSOR_AGENT_MODEL``／``CURSOR_AGENT_MODEL`` 傳入；**``auto``**（及空白）在 SDK 中改對應為 **``default``**（因 @cursor/sdk 不接受字面值 ``auto``）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_bridge: "_SdkStdioBridge | None" = None
_bridge_lock = asyncio.Lock()


def sdk_stdio_transport_enabled() -> bool:
	v = os.environ.get("BROWSER_USE_CURSOR_AGENT_TRANSPORT", "").strip().lower()
	return v in ("sdk_stdio", "sdk", "stdio_sdk", "1", "true", "yes", "on")


def _repo_node_dir() -> Path:
	"""browser_use_cursor_mcp/llm → repo/node"""
	return Path(__file__).resolve().parent.parent.parent / "node"


class _SdkStdioBridge:
	def __init__(self) -> None:
		self._proc: asyncio.subprocess.Process | None = None
		self._io_lock = asyncio.Lock()
		self._stderr_task: asyncio.Task[None] | None = None

	async def _drain_stderr(self) -> None:
		proc = self._proc
		if not proc or not proc.stderr:
			return
		try:
			while True:
				line = await proc.stderr.readline()
				if not line:
					break
				logger.debug("cursor sdk worker stderr: %s", line.decode("utf-8", errors="replace").rstrip())
		except Exception:
			pass

	async def ensure_started(self) -> None:
		if self._proc and self._proc.returncode is None:
			return
		node_dir = _repo_node_dir()
		worker = node_dir / "cursor_agent_sdk_worker.mjs"
		if not worker.is_file():
			raise RuntimeError(f"找不到 SDK worker：{worker}（請確認已 clone 本 repo）")
		if not (node_dir / "node_modules" / "@cursor" / "sdk").is_dir():
			raise RuntimeError(
				f"尚未安裝 Node 依賴：請在 {node_dir} 執行 `npm install`（需要 @cursor/sdk）。"
			)
		if not (os.environ.get("CURSOR_API_KEY") or "").strip():
			raise RuntimeError(
				"CURSOR_API_KEY 未設定。@cursor/sdk 需要 Dashboard Integrations 的 API Key（與 `agent login` 不同）。"
			)

		node_bin = (os.environ.get("NODE_BIN") or "node").strip() or "node"
		self._proc = await asyncio.create_subprocess_exec(
			node_bin,
			str(worker),
			stdin=asyncio.subprocess.PIPE,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
			cwd=str(node_dir),
			env=os.environ.copy(),
		)
		self._stderr_task = asyncio.create_task(self._drain_stderr())
		out = await self.request({"op": "ping"})
		if not (isinstance(out, dict) and out.get("ok")):
			raise RuntimeError(f"SDK worker ping 失敗：{out!r}")

	async def close(self) -> None:
		proc = self._proc
		self._proc = None
		if proc and proc.returncode is None:
			proc.kill()
			await proc.wait()
		if self._stderr_task:
			self._stderr_task.cancel()
			self._stderr_task = None

	async def request(self, msg: dict[str, Any]) -> dict[str, Any]:
		proc = self._proc
		if not proc or proc.stdin is None or proc.stdout is None:
			raise RuntimeError("SDK worker 未啟動")
		payload = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
		async with self._io_lock:
			proc.stdin.write(payload)
			await proc.stdin.drain()
			raw = await proc.stdout.readline()
		if not raw:
			code = proc.returncode
			raise RuntimeError(f"SDK worker 無回應（process returncode={code}）")
		try:
			return json.loads(raw.decode("utf-8"))
		except json.JSONDecodeError as e:
			raise RuntimeError(f"SDK worker 回傳非 JSON：{raw[:500]!r}") from e

	async def send_prompt(
		self,
		*,
		prompt: str,
		session_id: str | None,
		model: str,
		cwd: str,
	) -> str:
		sid = session_id.strip() if isinstance(session_id, str) and session_id.strip() else "default"
		out = await self.request(
			{
				"op": "send",
				"session_id": sid,
				"prompt": prompt,
				"model": model,
				"cwd": cwd,
			}
		)
		if not isinstance(out, dict) or not out.get("ok"):
			err = out.get("error") if isinstance(out, dict) else str(out)
			raise RuntimeError(f"SDK worker send 失敗：{err}")
		return str(out.get("result", ""))


async def get_sdk_stdio_bridge() -> _SdkStdioBridge:
	global _bridge
	async with _bridge_lock:
		if _bridge is None:
			_bridge = _SdkStdioBridge()
			await _bridge.ensure_started()
		return _bridge


async def shutdown_sdk_stdio_bridge() -> None:
	global _bridge
	async with _bridge_lock:
		if _bridge is not None:
			await _bridge.close()
			_bridge = None


async def dispose_sdk_session(session_id: str | None) -> None:
	"""釋放 worker 內對應 browser-use session 的 Cursor Agent（若 worker 尚未啟動則不做事）。"""
	global _bridge
	if _bridge is None:
		return
	sid = session_id.strip() if isinstance(session_id, str) and session_id.strip() else "default"
	try:
		await _bridge.request({"op": "dispose", "session_id": sid})
	except Exception:
		logger.debug("dispose_sdk_session 略過（worker 可能已關閉）", exc_info=True)
