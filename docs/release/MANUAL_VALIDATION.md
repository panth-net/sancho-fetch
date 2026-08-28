# Manual proprietary-client checks (optional)

Hosted CI proves the protocol fixtures, the hermetic lifecycle suite, and the
three-OS installed-wheel lifecycle. It cannot drive proprietary desktop GUIs.
Publishing does **not** wait on this checklist; run it when a release
advertises new behavior in a specific desktop client, and record the result in
the release notes.

Per client (Claude Desktop, ChatGPT/Codex, VS Code, Cursor), on a current
version: install/configure through `sancho setup`, restart if reported, run one
fetch, re-run setup, run `sancho doctor --fix`, then `sancho uninstall` and
confirm the entry is gone and data is preserved.

For the MCPB bundle, on a clean macOS or Windows profile with no Python, uv, or
Sancho: install the extension, complete first launch (downloads the pinned
package), fetch World Bank data, upgrade, uninstall, and confirm the external
workspace survives. Note that a new version's bundle only resolves after the
package has propagated on PyPI.

Never mark a check passed from config-file presence alone: launch the server
and exercise the step.
