#!/usr/bin/env node
// Sancho Fetch stdio shim for Claude Desktop (MCP Bundle entry point).
//
// Claude Desktop runs this with its bundled Node. All it does is find the
// user-level `sancho` command and hand the stdio stream to
// `sancho mcp serve --transport stdio`. Zero configuration: sancho resolves
// the registered library (~/.sancho/config.yaml) on its own.

"use strict";

const { spawn } = require("node:child_process");
const { existsSync } = require("node:fs");
const { join } = require("node:path");
const os = require("node:os");

function resolveSancho() {
  if (process.env.SANCHO_BIN && existsSync(process.env.SANCHO_BIN)) {
    return process.env.SANCHO_BIN;
  }
  const exe = process.platform === "win32" ? "sancho.exe" : "sancho";
  const stable = join(os.homedir(), ".local", "bin", exe);
  if (existsSync(stable)) {
    return stable;
  }
  // Last resort: let the OS search PATH.
  return "sancho";
}

const NOT_INSTALLED =
  "Sancho is not installed on this computer yet. Open your sancho-fetch " +
  "folder in an AI app (Claude Code tab or ChatGPT Codex) and paste: " +
  "\"Set up Sancho on this computer.\" Then re-enable this extension.";

const child = spawn(resolveSancho(), ["mcp", "serve", "--transport", "stdio"], {
  stdio: ["pipe", "pipe", "inherit"],
});

child.on("error", (err) => {
  process.stderr.write(`sancho-fetch extension: ${err.code === "ENOENT" ? NOT_INSTALLED : String(err)}\n`);
  process.exit(1);
});

child.on("exit", (code) => {
  process.exit(code === null ? 1 : code);
});

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);
