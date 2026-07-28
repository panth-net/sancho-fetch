"""Release-gate tests: ensure shipped artifacts stay in sync with code reality.

These tests catch:
1. Placeholder tokens that should have been replaced before release.
2. Module IDs in MODULE_PACKS that don't exist as template directories.
3. README pack tables that drift from the authoritative MODULE_PACKS dict.
4. API-key table entries that reference nonexistent modules.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

from sancho.module_packs import MODULE_PACKS

pytestmark = pytest.mark.release_gate


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "src" / "sancho" / "templates" / "modules"

PLACEHOLDER_TOKENS = [
    "[YOUR NAME OR ORG]",
    "[YOUR CONTACT]",
    "github.com/YOUR/repo",
]

SHIPPED_GLOBS = [
    "LICENSE",
    "README.md",
    "README_ALL_INSTRUCTIONS.md",
    "hosting/*.py",
    "hosting/*.txt",
    "hosting/*.md",
    "src/sancho/**/*.py",
]


def _all_template_module_ids() -> set[str]:
    """Return the set of module IDs that actually exist on disk."""
    ids: set[str] = set()
    for child in TEMPLATE_ROOT.iterdir():
        if child.is_dir() and (child / "module.yaml").exists():
            ids.add(child.name)
    return ids


# ── T1 gate: no placeholder tokens in shipped files ──────────────────────


def test_no_placeholder_tokens_in_shipped_files() -> None:
    offenders: list[str] = []
    for glob_pattern in SHIPPED_GLOBS:
        for path in ROOT.glob(glob_pattern):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for token in PLACEHOLDER_TOKENS:
                if token in text:
                    rel = path.relative_to(ROOT).as_posix()
                    offenders.append(f"{rel} contains '{token}'")

    assert not offenders, (
        "Placeholder tokens found in shipped files:\n  " + "\n  ".join(offenders)
    )


# ── T1b gate: no leaked credentials or personal identifiers in shipped files ─

# Query-string credentials with a concrete value. Recorded fetch errors and
# upstream catalog text must carry `key=REDACTED`, never a real value.
_CREDENTIAL_RE = re.compile(
    r"[?&](api_key|apikey|key|token|email)="
    r"(?!REDACTED\b|\{|%7B|\$|<|YOUR|your_|demo\b|DEMO_KEY\b|None\b|test\b)"
    r"[A-Za-z0-9%._+-]{6,}"
)
# Identity strings that must never ship: personal handles/emails and absolute
# home paths. `/Users/` is case-sensitive on purpose — lowercase `/users/` is a
# common public API path segment.
# Known-leaked identifier fragments, base64-encoded so this test file never
# contains them verbatim — the public repo must stay grep-clean for them.
_ENCODED_IDENTIFIERS = ["dGdvZXQ=", "dGhlby1nbw==", "cGFudGhlb254Z2xvYmFs"]
_IDENTITY_RES = [
    re.compile(
        "|".join(base64.b64decode(s).decode("utf-8") for s in _ENCODED_IDENTIFIERS),
        re.IGNORECASE,
    ),
    re.compile(r"%40gmail|@gmail", re.IGNORECASE),
    re.compile(r"/Users/"),
]
_LEAK_SCAN_ROOTS = [
    "src/sancho",
    "installers",
    "hosting",
    "integrations",
    "project-docs",
    "README.md",
    "README_ALL_INSTRUCTIONS.md",
    "AGENTS.md",
    "CLAUDE.md",
    "pyproject.toml",
    "LICENSE",
    "NOTICE",
]
_LEAK_SCAN_SUFFIXES = {
    ".py", ".json", ".md", ".yaml", ".yml", ".toml",
    ".sh", ".bat", ".txt", ".js", ".example",
}


def test_no_leaked_credentials_or_personal_identifiers() -> None:
    offenders: list[str] = []
    for entry in _LEAK_SCAN_ROOTS:
        base = ROOT / entry
        paths = [base] if base.is_file() else base.rglob("*")
        for path in paths:
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix not in _LEAK_SCAN_SUFFIXES and path.name != ".env.example":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, PermissionError):
                continue
            rel = path.relative_to(ROOT).as_posix()
            for match in _CREDENTIAL_RE.finditer(text):
                offenders.append(f"{rel}: credential-like value '{match.group(0)[:50]}'")
            for pattern in _IDENTITY_RES:
                for match in pattern.finditer(text):
                    offenders.append(f"{rel}: identity string '{match.group(0)}'")

    assert not offenders, (
        "Leaked credentials or personal identifiers in shipped files:\n  "
        + "\n  ".join(sorted(set(offenders)))
    )


def test_short_readme_points_ai_to_full_instructions() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "If you are an AI assistant" in readme
    assert "README_ALL_INSTRUCTIONS.md" in readme
    assert (ROOT / "README_ALL_INSTRUCTIONS.md").exists()


def test_readme_leads_with_pypi_install() -> None:
    """The very top of the README (the PyPI landing page) is the paste-to-AI
    install prompt: PyPI is the user path, the checkout is for contributors."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uv tool install sancho-fetch" in readme
    assert "uv tool upgrade sancho-fetch" in readme
    pypi_install = readme.index("uv tool install sancho-fetch")
    what_it_does = readme.index("## What it does")
    github_desktop = readme.index("GitHub Desktop")
    assert pypi_install < what_it_does, "install prompt must lead the page"
    assert pypi_install < github_desktop
    # PyPI renders the README with no repo context: the banner must be an
    # absolute URL or it shows as a broken image on the project page.
    first_image = readme.index("![")
    banner_src = readme[first_image : readme.index(")", first_image)]
    assert "https://" in banner_src, "banner image must be an absolute URL for PyPI"


def test_human_readmes_put_prerequisites_before_setup_steps() -> None:
    markers = {
        "README.md": "## Get started",
        "README_ALL_INSTRUCTIONS.md": "## Quick start (non-coders)",
    }
    for name, setup_marker in markers.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        prerequisites = text.index("## Before you begin")
        setup_steps = text.index(setup_marker)
        assert prerequisites < setup_steps, name
        section = text[prerequisites:setup_steps]
        assert "Python 3.11 or newer" in section
        assert "Node.js is optional" in section
        assert "API keys are not required" in section


def test_setup_instructions_highlight_computer_wide_code_sessions() -> None:
    paths = (
        ROOT / "README.md",
        ROOT / "README_ALL_INSTRUCTIONS.md",
        ROOT / "installers" / "setup.bat",
        ROOT / "installers" / "setup.sh",
        ROOT / "src" / "sancho" / "cli_setup.py",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        normalized = " ".join(text.replace(">", " ").split())
        assert "installed computer-wide" in normalized, path
        assert "Code tab" in normalized, path
        assert "Code chat" in normalized, path
        assert "Regular chats cannot access" in normalized, path


def test_env_instructions_cover_creation_and_hidden_files() -> None:
    docs = (ROOT / "README.md", ROOT / "README_ALL_INSTRUCTIONS.md")
    for path in docs:
        text = path.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        assert "copy `.env.example`" in normalized, path
        assert "name the copy `.env`" in normalized, path
        assert "sancho env open" in normalized, path
        assert "Cmd" in normalized and "Shift" in normalized, path
        assert "View" in normalized and "Show" in normalized and "Hidden items" in normalized, path

    for name in ("setup.bat", "setup.sh"):
        text = (ROOT / "installers" / name).read_text(encoding="utf-8")
        assert "sancho env open" in text, name
        assert "create it from .env.example" in text, name


def test_agent_docs_include_missing_sancho_setup_fallback() -> None:
    docs = [
        ROOT / "AGENTS.md",
        ROOT / "CLAUDE.md",
        ROOT / "src" / "sancho" / "templates" / "agent_skills" / "codex" / "skills" / "sancho" / "SKILL.md",
        ROOT / "src" / "sancho" / "templates" / "agent_skills" / "claude" / "skills" / "sancho" / "SKILL.md",
    ]
    missing: list[str] = []
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        if (
            "`sancho` command is missing" not in normalized
            # PyPI install is the primary fallback...
            or "uv tool install sancho-fetch" not in normalized
            # ...with the checkout installers retained for repo users.
            or "installers\\setup.bat" not in normalized
            or "bash installers/setup.sh" not in normalized
        ):
            missing.append(doc.relative_to(ROOT).as_posix())

    assert not missing, "Missing first-install fallback in:\n  " + "\n  ".join(missing)


def test_python_distribution_name_is_unique() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "sancho-fetch"' in pyproject
    assert 'sancho = "sancho.cli:main"' in pyproject


def test_clean_generated_script_exists() -> None:
    script = ROOT / "scripts" / "clean_generated.py"
    text = script.read_text(encoding="utf-8")
    assert "sancho-downloads" in text
    assert "__pycache__" in text


def test_primary_markdown_links_resolve() -> None:
    docs = [
        ROOT / "README.md",
        ROOT / "README_ALL_INSTRUCTIONS.md",
        ROOT / "project-docs" / "MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md",
        ROOT / "project-docs" / "MODULE_CREATION_GUIDE.md",
    ]
    missing: list[str] = []
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        for raw in link_re.findall(text):
            target = raw.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (doc.parent / target).resolve().exists():
                missing.append(f"{doc.relative_to(ROOT)} -> {raw}")
    assert not missing, "Broken markdown links:\n  " + "\n  ".join(missing)


# ── T2 gate: every pack module ID resolves to a real template dir ─────────


def test_all_pack_module_ids_exist_on_disk() -> None:
    on_disk = _all_template_module_ids()
    missing: list[str] = []
    for pack_name, module_ids in MODULE_PACKS.items():
        for mid in module_ids:
            if mid not in on_disk:
                missing.append(f"{pack_name} -> {mid}")

    assert not missing, (
        "MODULE_PACKS references modules not on disk:\n  " + "\n  ".join(missing)
    )


# ── T3 gate: README pack table matches MODULE_PACKS ──────────────────────


_PACK_NAME_RE = re.compile(r"\|\s*`(pack\.\w+)`\s*\|")


def _parse_readme_pack_names() -> set[str]:
    """Parse pack names from the pack table in README_ALL_INSTRUCTIONS.md.

    The table intentionally lists only pack name + focus; member lists come
    from `sancho packs --json`, so this gate checks name coverage only.
    """
    readme = (ROOT / "README_ALL_INSTRUCTIONS.md").read_text(encoding="utf-8")
    return set(_PACK_NAME_RE.findall(readme))


def test_readme_pack_table_matches_module_packs() -> None:
    readme_packs = _parse_readme_pack_names()
    missing = sorted(set(MODULE_PACKS) - readme_packs)
    stale = sorted(readme_packs - set(MODULE_PACKS))
    mismatches = [f"{name}: in MODULE_PACKS but not in README" for name in missing]
    mismatches += [f"{name}: in README but not in MODULE_PACKS" for name in stale]

    assert not mismatches, (
        "README pack table drifts from MODULE_PACKS:\n  " + "\n  ".join(mismatches)
    )


# ── T3 gate: API-key table entries reference real modules ─────────────────


_API_KEY_MODULE_RE = re.compile(r"`(fetch\.\S+?)`")


def _parse_readme_api_key_modules() -> set[str]:
    """Extract module IDs from the API key table in README_ALL_INSTRUCTIONS.md."""
    readme = (ROOT / "README_ALL_INSTRUCTIONS.md").read_text(encoding="utf-8")
    in_api_table = False
    modules: set[str] = set()
    for line in readme.splitlines():
        if "Env var" in line and "Provider" in line and "Used by" in line:
            in_api_table = True
            continue
        if in_api_table:
            if line.startswith("|"):
                for m in _API_KEY_MODULE_RE.findall(line):
                    if "*" not in m:
                        modules.add(m)
            elif not line.strip().startswith("|") and line.strip():
                break
    return modules


def test_support_matrix_is_current() -> None:
    """Ensure the published support matrix matches current code."""
    matrix_path = ROOT / "project-docs" / "SUPPORT_MATRIX.md"
    if not matrix_path.exists():
        pytest.skip("SUPPORT_MATRIX.md not yet generated")

    # Regenerate and compare
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_support_matrix import generate
    expected = generate()
    actual = matrix_path.read_text(encoding="utf-8")
    assert actual.strip() == expected.strip(), (
        "SUPPORT_MATRIX.md is stale. Regenerate with: "
        "python scripts/generate_support_matrix.py --write"
    )


def test_api_key_table_modules_exist() -> None:
    on_disk = _all_template_module_ids()
    api_modules = _parse_readme_api_key_modules()
    missing = sorted(api_modules - on_disk)
    assert not missing, (
        f"API key table references modules not on disk: {missing}"
    )
