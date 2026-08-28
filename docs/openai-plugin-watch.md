# OpenAI public-plugin watch gate

Status: **intentionally not built**

Sancho's supported OpenAI local path is `sancho setup`, which uses the Codex
MCP CLI and shared local Codex host configuration. Do not create or submit a
public OpenAI plugin while the submission runtime cannot represent either a
local stdio MCP server/bundled runtime or an explicit separately installed
Sancho CLI prerequisite.

Revisit only when current official submission documentation supports one of
those contracts. Record the documentation date, clean-environment behavior,
and review outcome before changing this gate.
