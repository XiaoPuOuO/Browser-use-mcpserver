/**
 * 長駐 stdio worker：一行一個 JSON 請求，一行一個 JSON 回應。
 * 以 @cursor/sdk 維持每個 browser-use session_id 一個 Agent，多步只送 agent.send，不再每步 exec `agent` CLI。
 *
 * 請求：{ op: "send", session_id: string, prompt: string, model: string, cwd: string }
 * 回應：{ ok: true, result: string } 或 { ok: false, error: string }
 *
 * 其他：{ op: "ping" } → { ok: true, pong: true }
 *      { op: "dispose", session_id: string } → 釋放該 session 的 Agent
 */

import * as readline from "node:readline";
import { Agent } from "@cursor/sdk";

const MAX_SESSIONS = Number(process.env.BROWSER_USE_CURSOR_SDK_MAX_SESSIONS || 24) || 24;

/** @type {Map<string, { agent: import("@cursor/sdk").SDKAgent, last: number }>} */
const sessions = new Map();

function touch(id) {
	const e = sessions.get(id);
	if (e) e.last = Date.now();
}

async function evictIfNeeded() {
	if (sessions.size <= MAX_SESSIONS) return;
	/** @type {Array<[string, number]>} */
	const ranked = [...sessions.entries()].map(([id, v]) => [id, v.last]);
	ranked.sort((a, b) => a[1] - b[1]);
	const victim = ranked[0]?.[0];
	if (!victim) return;
	await disposeOne(victim);
}

async function disposeOne(sessionId) {
	const e = sessions.get(sessionId);
	if (!e) return;
	sessions.delete(sessionId);
	try {
		await e.agent[Symbol.asyncDispose]();
	} catch {
		// ignore
	}
}

/**
 * @cursor/sdk 不接受字面值 ``auto``；與 CLI 的「自動選模」對應時改為 **default**（見 SDK 錯誤訊息中的可用 id）。
 * 空白同視為 auto → default。
 * @param {string} model
 * @returns {string}
 */
function normalizeModelForSdk(model) {
	const m = (model || "").trim();
	if (!m || m.toLowerCase() === "auto") {
		return "default";
	}
	return m;
}

/**
 * @param {any} msg
 */
async function handle(msg) {
	if (msg.op === "ping") {
		return { ok: true, pong: true };
	}
	if (msg.op === "dispose") {
		const sid = String(msg.session_id || "default");
		await disposeOne(sid);
		return { ok: true };
	}
	if (msg.op === "send") {
		const sessionId = String(msg.session_id || "default");
		const prompt = String(msg.prompt ?? "");
		const cwd = String(msg.cwd || process.cwd());
		const modelId = normalizeModelForSdk(String(msg.model || ""));

		if (!process.env.CURSOR_API_KEY?.trim()) {
			return { ok: false, error: "CURSOR_API_KEY 未設定；@cursor/sdk 需要 Dashboard Integrations 的 API Key。" };
		}

		await evictIfNeeded();

		let entry = sessions.get(sessionId);
		if (!entry) {
			const agent = await Agent.create({
				apiKey: process.env.CURSOR_API_KEY,
				model: { id: modelId },
				local: { cwd },
			});
			entry = { agent, last: Date.now() };
			sessions.set(sessionId, entry);
		}
		touch(sessionId);

		const run = await entry.agent.send(prompt, {
			model: { id: modelId },
			local: { force: true },
		});
		const rr = await run.wait();
		const text =
			(typeof rr.result === "string" && rr.result) ||
			(typeof run.result === "string" && run.result) ||
			"";
		return { ok: true, result: text };
	}
	return { ok: false, error: `未知 op: ${msg?.op}` };
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on("line", async (line) => {
	const trimmed = line.trim();
	if (!trimmed) return;
	let msg;
	try {
		msg = JSON.parse(trimmed);
	} catch (e) {
		process.stdout.write(JSON.stringify({ ok: false, error: `JSON 解析失敗: ${e}` }) + "\n");
		return;
	}
	try {
		const out = await handle(msg);
		process.stdout.write(JSON.stringify(out) + "\n");
	} catch (e) {
		process.stdout.write(
			JSON.stringify({ ok: false, error: e instanceof Error ? e.message : String(e) }) + "\n",
		);
	}
});
