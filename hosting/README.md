# Sancho Fetch Hosted Remote MCP Server

**If you are running Sancho Fetch locally (Claude Desktop, VS Code, Cursor, Windsurf, or the CLI), you do not need anything in this folder. This is only for deploying a public hosted remote-MCP endpoint.**

The hosted server is a **demo / classroom / event sampler**: a fetch-only,
stateless, rate-limited variant of Sancho Fetch for people using a browser
AI without installing anything. Free claude.ai accounts can connect
directly; free ChatGPT accounts use it through a shared GPT (see "Event
day" below). It is **deliberately stripped** -- whose main job is
to drive people to the real product (the local install).

## What hosted MCP cannot do

The hosted server is fundamentally limited compared to a local install:

- **No local cache.** Every request hits the upstream provider. The Phase
  3 fetched-data layout, `_catalog/` index, `cache-index.jsonl`, content
  hashes -- none of that exists on hosted. There is nothing to cache to.
- **No access to the user's Sancho Fetch folder.** The hosted instance
  has no `sancho-workspace/`, no `custom/`, no `playbooks/`, no `.env`
  beyond shared admin keys, no logs the user can read.
- **No analysis, dashboards, or downstream module types.** Only the
  fetch-allowlist runs (`src/sancho/mcp/hosted_allowlist.py`).
- **No high-level MCP tools** (`sancho_paths`, `sancho_inventory`,
  `sancho_cache_status`, `sancho_log_tail`, `sancho_update_*`, ...). These
  are explicitly gated on `policy.stateless=False` in
  `src/sancho/mcp/high_level_tools.py` -- they require a real workspace.
- **No project bundles.** `sancho_export_to_project` is local-only;
  hosted users can copy/paste a small response into their tool of choice.
- **No repair history.** No `logs/repairs.jsonl`, no error packets, no
  `sancho repair note`.
- **No custom overrides.** Users can't fix or customize anything; they
  use what's allowlisted.

The full product -- visible Sancho Fetch folder, cache, logs, repair
packets, update engine, project export, custom overrides -- requires the
local install: `sancho setup` from the Sancho Fetch folder.

Every hosted response ends with a nudge toward the local install for
exactly this reason.

## What users get

- A URL like `https://sancho-mcp.onrender.com/mcp` they paste into their MCP client.
- Access to a small allowlist of free, no-key-required data providers plus any shared admin keys you configure in the host environment.
- Every response ends with a nudge to install Sancho Fetch locally for the full product.

## What's protected

- **Per-IP rate limit** (default 20 req/min) in `limits.py`. In-memory, resets on container restart.
- **Response-size cap** (default 2 MB). Larger responses return a nudge message instead.
- **Request-size cap** (default 100 KB). Prevents payload-bomb DoS.
- **Allowlisted providers only** (see `src/sancho/mcp/hosted_allowlist.py`). No analysis, dashboards, or filesystem modules exposed.
- **Stateless execution.** No disk writes anywhere. Zero cross-user contamination.
- **No request-line logging.** `server.py` overrides `log_message` to no-op.

## Deploy (Render free web service)

1. Push this repo to GitHub.
2. Render -> New -> Web Service -> connect repo. It auto-detects `hosting/render.yaml`.
3. In the Render dashboard, add these secret env vars:
   - `CENSUS_API_KEY` -- your free Census API key, shared by the hosted demo.
   - Any other free provider keys you want to ship as fallbacks (e.g. `BLS_API_KEY`, `BEA_API_KEY`).
4. Deploy. Copy the `*.onrender.com` URL.
5. Test with a free claude.ai account and your shared GPT (below) before
   announcing.

## Event day: what attendees on FREE accounts can and cannot do

Plan gating as of July 2026 (verify before a big event; this changes):

- **Claude.ai (free plan): works directly.** Attendees sign in at claude.ai,
  go to **Settings -> Connectors -> Add custom connector**, paste your
  `https://<your-app>.onrender.com/mcp` URL, then enable it in a chat via
  the **+** menu. Free accounts are limited to ONE custom connector, and
  free-tier message limits apply. Put the URL on a slide or QR code.
- **ChatGPT (free plan): custom MCP connectors are NOT available.**
  Developer mode requires Plus or higher. The zero-cost-to-attendees path is
  a **shared GPT with Actions** (free signed-in users can use shared GPTs):
  1. You (one Plus account) open ChatGPT -> GPTs -> Create.
  2. In **Configure -> Actions -> Import from URL**, paste
     `https://<your-app>.onrender.com/openapi.json` (the server describes
     its own `listTools`/`callTool` facade).
  3. In Instructions, tell the GPT: "You fetch public data. Call listTools
     once to learn the available tools, then use callTool with arguments
     matching the tool's inputSchema. Present results as tables."
  4. Share the GPT by link. Attendees open the link signed in to any
     ChatGPT account, including free.
- **ChatGPT Plus attendees** can instead use the MCP URL directly:
  Settings -> Security and login -> enable Developer mode, then add the
  server under Settings -> Plugins.

**Do not put Cloudflare in front of the Render URL.** ChatGPT MCP connectors have documented compatibility issues with Cloudflare-proxied streamable HTTP. Use the direct `*.onrender.com` URL.

## Cold starts

Render's free tier sleeps after ~15 minutes of inactivity. First request after idle takes 20-40 seconds. This can exceed the MCP client handshake timeout, in which case the user will see a one-shot "connection failed" and the retry will succeed. This is a known limitation -- do not attempt keep-alive pings; they violate the free tier spirit and can get the service throttled.

## Secrets

- Never commit `.env` files. The root `.gitignore` should exclude them.
- Never put keys in `Dockerfile` or source code.
- Use Render's "Environment" tab for all secrets. They're injected at runtime and never printed to logs.

## Scope lock

This folder contains exactly what the hosted deploy needs. Do not add features beyond:

- Rate limiting
- Request/response size caps
- MCP `instructions` field with the install-locally nudge
- Dockerfile + Render config

Any feature request beyond those belongs in the local Sancho Fetch path (`src/sancho/`), not here.
