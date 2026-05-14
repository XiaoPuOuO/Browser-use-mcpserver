"""
以本機 Cursor `agent` CLI 子行程實作 browser_use.llm.base.BaseChatModel（Protocol）的 ainvoke。

browser-use 0.12+ 已不再使用 LangChain 的 BaseChatModel._generate；改為 async ainvoke。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar, overload

from pydantic import BaseModel, ValidationError

from browser_use.llm.base import BaseChatModel
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import (
	AssistantMessage,
	BaseMessage,
	ContentPartImageParam,
	ContentPartTextParam,
	SystemMessage,
	UserMessage,
)
from browser_use.llm.schema import SchemaOptimizer
from browser_use.llm.views import ChatInvokeCompletion, ChatInvokeUsage

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

# browser-use Agent.session_id（kwargs）→ Cursor `agent` JSON 外層的 `session_id`，供 `--resume` 重用
_resume_lock = asyncio.Lock()
_browser_use_session_to_cursor_resume: dict[str, str] = {}


def _resume_session_feature_enabled() -> bool:
	return os.environ.get("BROWSER_USE_CURSOR_AGENT_RESUME", "1").strip().lower() not in ("0", "false", "no", "off")


def _extract_cursor_resume_id_from_stdout(stdout: str) -> str | None:
	"""從 `agent --output-format json`  stdout 解析 Cursor 的 `session_id`（與 `result` 同層外層 JSON）。"""
	s = stdout.strip()
	blocks = [*[ln.strip() for ln in s.splitlines() if ln.strip()][::-1], s]
	for block in blocks:
		try:
			obj = json.loads(block)
		except json.JSONDecodeError:
			continue
		if not isinstance(obj, dict):
			continue
		sid = obj.get("session_id")
		if isinstance(sid, str) and sid.strip():
			return sid.strip()
	return None


async def _remember_cursor_resume_id(browser_use_session_id: str | None, stdout: str) -> None:
	if not browser_use_session_id or not _resume_session_feature_enabled():
		return
	cid = _extract_cursor_resume_id_from_stdout(stdout)
	if not cid:
		return
	async with _resume_lock:
		_browser_use_session_to_cursor_resume[browser_use_session_id] = cid


async def _forget_cursor_resume_id(browser_use_session_id: str | None) -> None:
	if not browser_use_session_id:
		return
	async with _resume_lock:
		_browser_use_session_to_cursor_resume.pop(browser_use_session_id, None)


async def _get_stored_cursor_resume_id(browser_use_session_id: str | None) -> str | None:
	if not browser_use_session_id or not _resume_session_feature_enabled():
		return None
	async with _resume_lock:
		return _browser_use_session_to_cursor_resume.get(browser_use_session_id)


def _strip_code_fence(text: str) -> str:
	s = text.strip()
	m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
	if m:
		return m.group(1).strip()
	return s


def _unwrap_cursor_agent_stdout(stdout: str) -> str:
	"""
	Cursor ``agent --output-format json`` 常見輸出：

	- 單行 ``{"type":"result","result":"...可能含前綴文字與內嵌 JSON..."}``
	- 或 stream-json 多行：自**最後一行**往前找，第一個可 parse 且為 ``type==result`` 者剥 ``result``。
	若無此包裝，回傳原 ``stdout``（供直接擷取 ``AgentOutput`` JSON）。
	"""
	s = stdout.strip()
	lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
	candidates = lines[::-1] + [s] if lines else [s]
	for block in candidates:
		try:
			outer = json.loads(block)
		except json.JSONDecodeError:
			continue
		if isinstance(outer, dict) and outer.get("type") == "result" and isinstance(outer.get("result"), str):
			return outer["result"].strip()
	return s


def _extract_json_for_pydantic(text: str, model_cls: type[BaseModel]) -> str:
	"""
	從可能含前綴說明的文字中，找出可 ``model_validate_json`` 的 JSON 物件字串。

	1. 優先：由尾端掃描 ``{``，若 ``raw_decode`` 後僅剩空白且驗證通過（常見：說明 + 末尾純 JSON）。
	2. 否則：嘗試每個 ``{`` 起頭的子字串，取**最長**且通過驗證者（避免誤用外層包裝 JSON）。
	"""
	text = _strip_code_fence(text)
	decoder = json.JSONDecoder()

	for i in range(len(text) - 1, -1, -1):
		if text[i] != "{":
			continue
		try:
			_, end = decoder.raw_decode(text[i:])
			if text[i + end :].strip() != "":
				continue
			slice_ = text[i : i + end]
			model_cls.model_validate_json(slice_)
			return slice_
		except (json.JSONDecodeError, ValueError, ValidationError):
			continue

	best: str | None = None
	best_len = -1
	for i, ch in enumerate(text):
		if ch != "{":
			continue
		try:
			_, end = decoder.raw_decode(text[i:])
			slice_ = text[i : i + end]
			model_cls.model_validate_json(slice_)
			if len(slice_) > best_len:
				best_len = len(slice_)
				best = slice_
		except (json.JSONDecodeError, ValueError, ValidationError):
			continue
	if best is None:
		raise ValueError(f"找不到可驗證為 {model_cls.__name__} 的 JSON 物件")
	return best


def _plaintext_agent_output_fallback_enabled() -> bool:
	return os.environ.get("BROWSER_USE_CURSOR_AGENT_PLAINTEXT_FALLBACK", "1").strip().lower() not in (
		"0",
		"false",
		"no",
		"off",
	)


def _parse_cursor_result_envelope(stdout: str) -> dict[str, Any] | None:
	"""自 stdout 最後可 parse 的 JSON 區塊讀取 Cursor ``type==result`` 外層物件（若有）。"""
	s = stdout.strip()
	blocks = [*[ln.strip() for ln in s.splitlines() if ln.strip()][::-1], s]
	for block in blocks:
		try:
			obj = json.loads(block)
		except json.JSONDecodeError:
			continue
		if isinstance(obj, dict) and obj.get("type") == "result":
			return obj
	return None


def _synthesize_agent_output_from_plain_text(output_format: type[BaseModel], text: str) -> BaseModel:
	"""
	當 ``agent`` 僅回覆自然語言／Markdown、未含可驗證的 ``AgentOutput`` JSON 時，
	包成單一 ``done`` 動作，讓 browser-use 能結束步驟或繼續流程。
	"""
	max_len = 150_000
	t = text if len(text) <= max_len else text[: max_len] + "\n…(已截斷)"
	note = "Cursor agent 未依 schema 輸出 JSON；以下為其原始文字，已對應為 done。"
	done_action: dict[str, Any] = {"done": {"text": t, "success": True, "files_to_display": []}}
	candidates: list[dict[str, Any]] = [
		{
			"evaluation_previous_goal": note,
			"memory": "",
			"next_goal": "",
			"action": [done_action],
		},
		{"memory": note, "action": [done_action]},
	]
	last_err: ValidationError | None = None
	for body in candidates:
		try:
			return output_format.model_validate(body)  # type: ignore[return-value]
		except ValidationError as ve:
			last_err = ve
			continue
	assert last_err is not None
	raise last_err


def _serialize_messages(
	messages: Sequence[BaseMessage],
	*,
	image_paths: list[Path],
) -> str:
	"""
	將 browser-use 的訊息序列成單一文字 prompt（含截圖檔路徑，避免把巨大 base64 塞進 argv）。
	"""
	lines: list[str] = []
	for msg in messages:
		if isinstance(msg, SystemMessage):
			role = "system"
			body = msg.text
		elif isinstance(msg, UserMessage):
			role = "user"
			body = _serialize_user_content(msg, image_paths)
		elif isinstance(msg, AssistantMessage):
			role = "assistant"
			body = msg.text
			if msg.tool_calls:
				body += "\n\n[tool_calls JSON]\n" + json.dumps(
					[
						{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
						for tc in msg.tool_calls
					],
					ensure_ascii=False,
				)
		else:
			role = "unknown"
			body = str(msg)
		lines.append(f"### {role.upper()}\n{body}")
	if image_paths:
		lines.insert(
			0,
			"下列為本回合附帶的頁面截圖檔案路徑（請依文字與檔案推理下一步）：\n"
			+ "\n".join(f"- {p}" for p in image_paths),
		)
	return "\n\n".join(lines)


def _serialize_user_content(msg: UserMessage, image_paths: list[Path]) -> str:
	c = msg.content
	if isinstance(c, str):
		return c
	parts: list[str] = []
	for part in c:
		if isinstance(part, ContentPartTextParam):
			parts.append(part.text)
		elif isinstance(part, ContentPartImageParam):
			url = part.image_url.url
			path = _write_image_sidecar(url, len(image_paths))
			image_paths.append(path)
			parts.append(f"[screenshot file: {path}]")
	return "\n".join(parts)


def _write_image_sidecar(data_url_or_path: str, seq: int) -> Path:
	"""將 data URL 圖片寫入暫存檔並回傳路徑。"""
	if data_url_or_path.startswith("data:"):
		try:
			header, b64 = data_url_or_path.split(",", 1)
			raw = base64.b64decode(b64)
		except (ValueError, binascii.Error) as e:
			raise ModelProviderError(message=f"無法解碼圖片 data URL: {e}", model="cursor-agent-cli") from e
		suffix = ".png" if "png" in header.lower() else ".jpg"
		fd, name = tempfile.mkstemp(prefix=f"bu-screenshot-{seq}-", suffix=suffix)
		os.close(fd)
		p = Path(name)
		p.write_bytes(raw)
		return p
	p = Path(data_url_or_path)
	if p.is_file():
		return p
	raise ModelProviderError(message=f"非預期的 image_url: {data_url_or_path[:80]}…", model="cursor-agent-cli")


def _default_cursor_agent_model() -> str:
	"""對應 `agent --model`；未設定時為 Cursor 建議的 auto。"""
	return (os.environ.get("BROWSER_USE_CURSOR_AGENT_MODEL") or os.environ.get("CURSOR_AGENT_MODEL") or "auto").strip()


@dataclass
class ChatCursorAgentCLI(BaseChatModel):
	"""
	透過子行程呼叫 Cursor `agent` CLI（預設指令名稱 `agent`），模擬 chat completion。

	需已在本機完成登入：`agent login`。

	模型由環境變數 **BROWSER_USE_CURSOR_AGENT_MODEL** 或 **CURSOR_AGENT_MODEL** 指定（預設 **auto**），
	會以 ``agent --model <值>`` 傳入；可用 ``agent --list-models`` 查看可用 id。

	非互動呼叫時會自動加上 **``--yolo``**（等同 ``--force``，減少互動阻擋）與 **``--trust``**
	（搭配 ``--print`` 時略過 workspace 信任提示），供 MCP／自動化使用。

	若 browser-use 傳入 ``session_id``（kwargs），會把 Cursor ``agent`` 回傳外層 JSON 的 ``session_id`` 記住，
	後續同一個 browser-use 工作階段的 ``ainvoke`` 會加上 ``--resume <id>`` 以重用對話（可用環境變數
	``BROWSER_USE_CURSOR_AGENT_RESUME=0`` 關閉）。

	若 ``agent`` 的 ``result`` 僅為說明文字而無內嵌 ``AgentOutput`` JSON，預設會自動包成 ``done`` 動作
	（環境變數 ``BROWSER_USE_CURSOR_AGENT_PLAINTEXT_FALLBACK=0`` 可關閉，改為嚴格解析失敗即報錯）。
	"""

	model: str = field(default_factory=_default_cursor_agent_model)
	command: str = field(default_factory=lambda: os.environ.get("CURSOR_AGENT_CMD", "agent"))
	extra_args: list[str] = field(default_factory=list)
	timeout_sec: float = 600.0
	"""單次 LLM 呼叫逾時（秒）。複雜頁面／長對話建議調大。"""

	_verified_api_keys: bool = False

	@property
	def provider(self) -> str:
		return "cursor-agent-cli"

	@property
	def name(self) -> str:
		return str(self.model)

	def _resolve_executable(self) -> str:
		cmd = self.command
		if os.sep in cmd or (os.altsep and os.altsep in cmd):
			return cmd
		found = shutil.which(cmd)
		if not found:
			raise ModelProviderError(
				message=(
					f"找不到可執行檔 `{cmd}`。請確認已安裝 Cursor CLI 並在 PATH 中，"
					"或設定環境變數 CURSOR_AGENT_CMD 為完整路徑。"
				),
				status_code=500,
				model=self.name,
			)
		return found

	@overload
	async def ainvoke(
		self,
		messages: list[BaseMessage],
		output_format: None = None,
		**kwargs: Any,
	) -> ChatInvokeCompletion[str]: ...

	@overload
	async def ainvoke(
		self,
		messages: list[BaseMessage],
		output_format: type[T],
		**kwargs: Any,
	) -> ChatInvokeCompletion[T]: ...

	async def ainvoke(
		self,
		messages: list[BaseMessage],
		output_format: type[T] | None = None,
		**kwargs: Any,
	) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
		raw_sid = kwargs.get("session_id")
		if isinstance(raw_sid, str) and raw_sid.strip():
			bu_session: str | None = raw_sid.strip()
		else:
			bu_session = None

		image_paths: list[Path] = []
		try:
			serialized = _serialize_messages(messages, image_paths=image_paths)
			if output_format is not None:
				schema = SchemaOptimizer.create_optimized_json_schema(output_format)
				serialized += (
					"\n\n---\n你必須只輸出一個 JSON 物件（不要 markdown、不要說明文字），"
					"且需完全符合下列 JSON Schema（欄位名稱與型別必須一致）：\n"
					f"{json.dumps(schema, ensure_ascii=False)}"
					"\n\n若動作為 `done`：`files_to_display` 只能填 **browser-use 檔案工作區內**已建立的檔名；"
					"**禁止**把本機絕對路徑（例如 `/Users/.../x.png`）放進此陣列（無法顯示且會觸發執行時警告）。"
					"沒有要附檔時請填 `[]`，檔案路徑僅寫在 `text` 說明中即可。"
				)

			cursor_resume_id = await _get_stored_cursor_resume_id(bu_session)
			used_resume = bool(cursor_resume_id)

			exe = self._resolve_executable()
			cmd: list[str] = [exe, *self.extra_args]
			if cursor_resume_id:
				cmd.extend(["--resume", cursor_resume_id])
			if self.model:
				cmd.extend(["--model", self.model])
			# 非互動：略過 workspace 信任提示；--yolo 等同 --force，降低 CLI 互動阻擋
			cmd.extend(["--yolo", "--trust", "--print", "--output-format", "json", serialized])

			proc = await asyncio.create_subprocess_exec(
				*cmd,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
				env=os.environ.copy(),
			)
			try:
				stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_sec)
			except TimeoutError as e:
				proc.kill()
				if used_resume and bu_session:
					await _forget_cursor_resume_id(bu_session)
				raise ModelProviderError(
					message=f"agent CLI 逾時（{self.timeout_sec}s）",
					status_code=504,
					model=self.name,
				) from e

			stdout = stdout_b.decode("utf-8", errors="replace")
			stderr = stderr_b.decode("utf-8", errors="replace")

			if proc.returncode != 0:
				if used_resume and bu_session:
					await _forget_cursor_resume_id(bu_session)
				raise ModelProviderError(
					message=f"agent CLI 結束碼 {proc.returncode}。stderr:\n{stderr[-4000:]}",
					status_code=502,
					model=self.name,
				)

			usage = ChatInvokeUsage(
				prompt_tokens=0,
				prompt_cached_tokens=None,
				prompt_cache_creation_tokens=None,
				prompt_image_tokens=None,
				completion_tokens=0,
				total_tokens=0,
			)

			if output_format is None:
				text = stdout.strip()
				if not text:
					raise ModelProviderError(message="agent CLI 未輸出內容", status_code=502, model=self.name)
				try:
					wrapper = json.loads(text)
					if isinstance(wrapper, dict) and "result" in wrapper:
						text = str(wrapper["result"])
				except json.JSONDecodeError:
					pass
				await _remember_cursor_resume_id(bu_session, stdout)
				return ChatInvokeCompletion(completion=text, usage=usage, stop_reason="stop")

			try:
				payload = _unwrap_cursor_agent_stdout(stdout)
				json_str = _extract_json_for_pydantic(payload, output_format)
				parsed = output_format.model_validate_json(json_str)
			except (ValueError, json.JSONDecodeError, ValidationError) as e:
				envelope = _parse_cursor_result_envelope(stdout)
				if envelope is not None and envelope.get("is_error") is True:
					raise ModelProviderError(
						message=(
							f"無法將 agent 輸出解析為 {output_format.__name__}: {e}\n"
							"（且 Cursor 外層 is_error=true，不使用純文字後備）\n"
							f"--- stdout ---\n{stdout[-8000:]}"
						),
						status_code=500,
						model=self.name,
					) from e
				if _plaintext_agent_output_fallback_enabled() and isinstance(payload, str) and payload.strip():
					try:
						parsed = _synthesize_agent_output_from_plain_text(output_format, payload.strip())
					except ValidationError as ve:
						raise ModelProviderError(
							message=(
								f"無法將 agent 輸出解析為 {output_format.__name__}: {e}\n"
								f"純文字後備亦失敗: {ve}\n--- stdout ---\n{stdout[-8000:]}"
							),
							status_code=500,
							model=self.name,
						) from ve
					logger.warning(
						"agent CLI 的 result 無可驗證的 %s JSON，已將純文字包成 done（可用 "
						"BROWSER_USE_CURSOR_AGENT_PLAINTEXT_FALLBACK=0 關閉）",
						output_format.__name__,
					)
				else:
					raise ModelProviderError(
						message=f"無法將 agent 輸出解析為 {output_format.__name__}: {e}\n--- stdout ---\n{stdout[-8000:]}",
						status_code=500,
						model=self.name,
					) from e

			await _remember_cursor_resume_id(bu_session, stdout)
			return ChatInvokeCompletion(completion=parsed, usage=usage, stop_reason="stop")
		finally:
			for p in image_paths:
				try:
					if p.is_file():
						p.unlink(missing_ok=True)
				except OSError:
					pass
