#!/usr/bin/env node
import { spawnSync } from "node:child_process";

const uvx = process.platform === "win32" ? "uvx.exe" : "uvx";
const check = spawnSync(uvx, ["--version"], { stdio: "pipe" });
if (check.status !== 0 || check.error) {
  console.error("Error: 'uv' is not installed or not on PATH.");
  console.error("Install uv: https://docs.astral.sh/uv/");
  console.error("Then retry this command.");
  process.exit(1);
}

const args = process.argv.slice(2);
const result = spawnSync(uvx, ["--from", "sancho-fetch", "sancho", ...args], {
  stdio: "inherit",
});

if (typeof result.status === "number") {
  process.exit(result.status);
}
process.exit(1);
