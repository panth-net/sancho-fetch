![Sancho Fetch](https://raw.githubusercontent.com/panth-net/sancho-fetch/master/project-docs/assets/banner.jpg)

# Sancho Fetch

<!-- mcp-name: io.github.panth-net/sancho-fetch -->

Ask your AI for public data. Get real files on your computer.

## The fastest way in: tell your AI

Open your AI's code mode -- **Claude** desktop app -> **Code** tab, or
**ChatGPT** desktop app -> **Codex** -- pick any folder, and paste this:

> Install Sancho Fetch from PyPI (`uv tool install sancho-fetch`) and set it
> up on this computer. If `uv` isn't installed, tell me, then install it
> first. When you're done, tell me whether the install succeeded. Then
> explain in plain English, no jargon: what the .env file is, how to use it,
> where it is on my computer, and open it for me so I can paste API keys
> straight into it. Give me a few examples of data sources that need a free
> API key and a few examples of sources that don't need a key. Tell me where
> my downloaded data gets saved, and how I update Sancho later. Then run a
> short example data fetch using the World Bank so I can see where the data
> was saved. Finally tell me a few natural language examples I can tell you
> to fetch data so I can get a feel for how to use sancho-fetch and remind
> me that 1) I can use it anywhere as long as I'm in a LLM Desktop app's
> Code tab (e.g. ChatGPT Desktop or Claude Desktop), and 2) that I can ask
> AI to add new data sources by itself since sancho-fetch is built in a way
> that it's easily extensible (aka you can add more to it and the AI will do
> the heavy lifting and connect the new data source).

That's the whole install.

You do **not** need to download or clone this repository. The two commands the
AI runs are:

```bash
uv tool install sancho-fetch
sancho setup
```

**Install once, use everywhere.** Sancho installs once on your computer and
connects to the AI apps it finds (Claude Desktop, ChatGPT/Codex, VS Code,
Cursor). At the end of setup it tells you plainly which apps are ready and
which just need a restart or a click.

To use Sancho, just ask for data and mention "sancho" in plain English, or type **`/sancho`** in Claude Code to feel cool.

## What it does

- In your AI's Code mode you ask: *"get county-level asthma rates for Ohio."*
  You can be working in any folder -- Sancho always knows where its home
  folder is.
- Your AI uses Sancho to pull from 120+ public sources (Census, World Bank,
  FDA, USGS, FEMA, ...) and hands you a file that opens in Excel.
- Everything is saved on your computer.

## Before you begin

The normal prerequisite is [`uv`](https://docs.astral.sh/uv/). `uv` installs
Sancho in isolation and can obtain a compatible Python without replacing your
computer's system Python. First setup needs an internet connection. API keys
are not required for installation or the World Bank example; provider-specific
keys can be added later.

## Get started (about 2 minutes)

Install straight from PyPI.

**1. Open your AI's code mode.**

- **Claude:** Claude desktop app -> **Code** tab -> new session -> pick any folder where you want your data to live.
- **ChatGPT:** ChatGPT desktop app -> **Codex** -> open that folder.

**2. Paste the install request from the top of this page.**

The AI installs everything, shows you your first data file, and walks you
through where everything lives.

**3. Restart the apps Sancho asks you to restart.** Setup ends with a short
report; if an app needs a restart or one extra click, it says so in plain
words.

NOTE: Before using, make sure to add API keys for any sources you want to use. 

Many sources need no key (World Bank, USGS, FEMA, openFDA, ...). Your AI will tell you when an API key is needed.
You can either:

1. Open the `.env` file in the `sancho-workspace` folder and paste your key there; or
2. Ask your AI to open the keys file for you (`sancho env open`). Paste the key into the opened file, **don't paste your key 
into the chat**. 

Setup normally creates `.env` from `.env.example`. If `.env` is missing,
`sancho env open` creates and opens it. To do this manually, copy
`.env.example` in the same folder, keep the original template, and name the
copy `.env`.

Both files may be hidden:

- **macOS Finder:** press `Cmd+Shift+.` (Command + Shift + period).
- **Windows File Explorer:** select **View -> Show -> Hidden items**.

@Developers, fyi Sancho is designed to read key names only, not values.

<details>
<summary><strong>Prefer the GitHub repository, or installing without an AI app?</strong></summary>

For contributing, custom module development, or offline installs, work from
the repository folder instead. Install
[GitHub Desktop](https://desktop.github.com/) (free), then on this
repository's page click **Code** -> **Open with GitHub Desktop** ->
**Clone**.

Note: Avoid placing the Github folder in a folder that is within iCloud/OneDrive (e.g. Documents folder in iCloud). This causes issues with file syncing and speed.

Then double-click `installers/Install Sancho.command` (macOS) or
`installers/Install Sancho.bat` (Windows); on Linux run
`bash installers/setup.sh`.

- macOS blocks the first open (the installer is not notarized): **System
  Settings -> Privacy & Security** -> scroll to the blocked-file message ->
  **Open Anyway** -> open it again.
- Windows: at "Windows protected your PC", click **More info** ->
  **Run anyway**.

</details>

## Everyday use

- In Claude Code / Codex, just ask for data. In Claude Code you can also
  type **`/sancho`** and **`/sancho-update`** directly.

> **After installation, use a Code session.** Sancho is installed
> computer-wide, so you do not need to add the `sancho-fetch` folder in future
> sessions. In **Claude Desktop, select the Code tab**. In **Codex, start a
> Code chat**. Regular chats cannot access your local Sancho installation.


- There are system instructions to make Sancho return non-technical details of each data pull, so if you want these technical details returned, tell your AI:

>  *"turn on Sancho developer mode."*

- Something off? Ask your AI to run `sancho ready` -- it checks your setup and
  reports what's wrong, without changing your setup. To actually fix problems,
  ask your AI to run `sancho doctor --fix`.

## Where your files land

```text
your folder/
  sancho-downloads/    # <-- files you have downloaded via chatting with AI
  sancho-workspace/
    source/            # managed data modules
    custom/            # your own modules -- never overwritten when updating Sancho
    playbooks/         # your repeatable workflows
    fetched-data/      # faithful archive of every fetch (don't edit - this is a cache so we don't have to use API calls unnecessarily)
    analysis-data/     # your derived work
    outputs/           # reports, dashboards, exports
    logs/              # what Sancho did, when, and why
    update-backups/    # snapshots before every update
    .env               # your API keys (never logged, never printed)
```

Every fetch writes a **working file you open** -- into `sancho-downloads/` in the folder that you're working in -- and a **faithful archive/cache copy** in `sancho-workspace/fetched-data/` so repeat requests reuse cached data. 

Tables arrive as Excel `.xlsx` with codes like
`01003` kept intact; maps stay GeoJSON/KML; nothing is converted in a way
that loses information. Filenames start with the date:
`2026-06-08_194211_alabama-population.xlsx`.


## Add your own data sources

Tell your AI:

> Create a Sancho module for [that API / that agency's data / this file I
> receive every month].

It's built under `custom/`, works like the built-in sources, and Sancho updates never overwrite the folder.

A good example of this is, Sancho fetches from Washington DC's and New York City's open data portals, which use a common API/open data portal format. The AI can be asked to create a module for other cities and will intelligently check on its own whether the new city uses the same format or not, and if it does, will reuse the same module code format (and otherwise, create a new one). **You'd be surprised at how many cities use the same format so give it a try if you're working in a geographic regional level that is not already covered by Sancho's built-in modules.**

## Updates

Just ask your AI:

> Update Sancho.

The AI upgrades the `sancho` command from PyPI (`uv tool upgrade sancho-fetch`)
and then migrates your workspace safely, with a backup and a rollback command.

Working from the GitHub repository instead? In GitHub Desktop: **Fetch
origin -> Pull origin**, then tell your AI *"update Sancho."*

When updating, your own files (`custom/`, `playbooks/`, `fetched-data/`, `.env`,
...) are never touched. 

If you want Sancho to stop mentioning new versions in chats (which it will do once every 2 weeks), simply set `SANCHO_UPDATE_NUDGE=false` in `.env` to turn it off.


## Uninstalling

Same as installing: paste one request to your AI in a Code session:

> Uninstall Sancho Fetch from this computer: run `sancho uninstall`, then
> `uv tool uninstall sancho-fetch`. Keep my `sancho-workspace` and
> `sancho-downloads` folders -- that is my data and my API keys. Tell me when
> it's done and what was removed.

(Those two commands are the whole uninstall if you'd rather run them yourself.)

Sancho only removes what it installed: its skills and its entries in your AI
apps. Anything you edited or created yourself is left alone and reported.

Your `sancho-workspace/` folder (fetched data, custom modules, `.env` keys) and
your `sancho-downloads/` files are **always kept**. Deleting data is a
separate, deliberate step that asks for confirmation first -- ask your AI, or
run `sancho uninstall --help` to see how.

## More documentation

- [`CHANGELOG.md`](CHANGELOG.md) -- what changed in each release.
- [`README_ALL_INSTRUCTIONS.md`](README_ALL_INSTRUCTIONS.md) -- full
  operator/AI reference.
- [`project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md`](project-docs/MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md) --
  MCP setup details for desktop and web clients.
- [`project-docs/MODULE_CREATION_GUIDE.md`](project-docs/MODULE_CREATION_GUIDE.md) --
  how your AI builds new data modules.

## Hosting your own version of Sancho

While Sancho is designed to run on your own computer, you can also host it on a server so that users can access it via web rather than needing Claude/Codex desktop apps. 

The idea with hosting was primarily to support organizations hosting hands-on workshops for users who may not have the technical skills to install Sancho on their own computers.

- [`hosting/README.md`](hosting/README.md) -- hosted demo endpoint for events.

## For AI assistants

If you are an AI assistant, do not operate from this quick start. Read
[`README_ALL_INSTRUCTIONS.md`](README_ALL_INSTRUCTIONS.md), then follow
[`CLAUDE.md`](CLAUDE.md) or [`AGENTS.md`](AGENTS.md).

## License

Code is licensed under Apache 2.0; documentation under CC BY 4.0 unless
noted. The Sancho name, logo, and brand assets are protected separately --
see [LICENSE](./LICENSE), [NOTICE](./NOTICE),
[LICENSE-DOCS.md](./LICENSE-DOCS.md), and [INTENDED_USE.md](./INTENDED_USE.md).
