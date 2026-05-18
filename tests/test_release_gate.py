"""Release-gate tests: ensure shipped artifacts stay in sync with code reality.

These tests catch:
1. Placeholder tokens that should have been replaced before release.
2. Module IDs in MODULE_PACKS that don't exist as template directories.
3. README pack tables that drift from the authoritative MODULE_PACKS dict.
4. API-key table entries that reference nonexistent modules.
"""

from __future__ import annotations

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


def test_short_readme_points_ai_to_full_instructions() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "If you are an AI assistant" in readme
    assert "README_ALL_INSTRUCTIONS.md" in readme
    assert (ROOT / "README_ALL_INSTRUCTIONS.md").exists()


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
    assert "sancho-fetched-data" in text
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


_PACK_TABLE_RE = re.compile(
    r"\|\s*`(pack\.\w+)`\s*\|[^|]*\|\s*([^|]+)\|"
)


def _parse_readme_pack_table() -> dict[str, set[str]]:
    """Parse pack tables from README_ALL_INSTRUCTIONS.md, return {pack_name: {module_ids}}."""
    readme = (ROOT / "README_ALL_INSTRUCTIONS.md").read_text(encoding="utf-8")
    result: dict[str, set[str]] = {}
    for match in _PACK_TABLE_RE.finditer(readme):
        pack_name = match.group(1)
        modules_cell = match.group(2)
        module_ids = set(re.findall(r"`(fetch\.\S+?)`", modules_cell))
        if module_ids:
            result[pack_name] = module_ids
    return result


def test_readme_pack_tables_match_module_packs() -> None:
    readme_packs = _parse_readme_pack_table()
    mismatches: list[str] = []
    for pack_name in sorted(set(readme_packs) | set(MODULE_PACKS)):
        readme_modules = readme_packs.get(pack_name)
        if readme_modules is None:
            mismatches.append(f"{pack_name}: in MODULE_PACKS but not in README")
            continue
        if pack_name not in MODULE_PACKS:
            mismatches.append(f"{pack_name}: in README but not in MODULE_PACKS")
            continue
        code_modules = set(MODULE_PACKS[pack_name])
        if readme_modules != code_modules:
            only_readme = readme_modules - code_modules
            only_code = code_modules - readme_modules
            parts = []
            if only_readme:
                parts.append(f"README-only: {sorted(only_readme)}")
            if only_code:
                parts.append(f"code-only: {sorted(only_code)}")
            mismatches.append(f"{pack_name}: {'; '.join(parts)}")

    assert not mismatches, (
        "README pack tables drift from MODULE_PACKS:\n  " + "\n  ".join(mismatches)
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
