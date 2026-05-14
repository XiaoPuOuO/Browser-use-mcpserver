#!/usr/bin/env node
/**
 * 以 Node child_process.spawn 啟動 Python MCP（stdio 繼承父行程）。
 * 供希望在 MCP 設定中明確由 Node 發起子行程的情境使用。
 */
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

// 使用 --project 鎖定 repo，避免 Cursor 以錯誤 cwd 或系統 python 導致 No module named browser_use_cursor_mcp
const child = spawn("uv", ["run", "--project", root, "python", "-m", "browser_use_cursor_mcp"], {
	stdio: "inherit",
	env: process.env,
	shell: false,
});

child.on("error", (err) => {
	console.error("[mcp-stdio-bridge]", err);
	process.exit(1);
});

child.on("exit", (code, signal) => {
	if (signal) process.exit(1);
	process.exit(code ?? 0);
});
