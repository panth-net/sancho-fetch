"""Phase 7 skill fixture tests — make sure the agent guidance files ship intact."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_TEMPLATES = ROOT / "src" / "sancho" / "templates" / "agent_skills"


def test_claude_code_sancho_skill_exists_with_required_pieces() -> None:
    skill = SKILL_TEMPLATES / "claude" / "skills" / "sancho" / "SKILL.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    # Required frontmatter
    assert text.startswith("---")
    assert "name: sancho" in text
    assert "description:" in text
    # Required skill flow steps
    for must_have in (
        "sancho mode",
        "sancho paths",
        "sancho find sources",
        "sancho module show",
        "sancho cache status",
        "sancho run",
        "sancho log tail",
        "sancho export-to-project",
    ):
        assert must_have in text, f"skill missing reference to {must_have}"
    # $ARGUMENTS contract
    assert "$ARGUMENTS" in text


def test_codex_sancho_skill_exists_with_required_pieces() -> None:
    skill = SKILL_TEMPLATES / "codex" / "skills" / "sancho" / "SKILL.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: sancho" in text
    assert "description:" in text
    for must_have in (
        "AGENTS.md",
        "sancho mode",
        "sancho paths",
        "sancho find sources",
        "sancho log tail",
        "logs/errors/",
    ):
        assert must_have in text


def test_skills_are_bundled_for_packaged_setup() -> None:
    bundled = [
        SKILL_TEMPLATES / "claude" / "skills" / "sancho" / "SKILL.md",
        SKILL_TEMPLATES / "claude" / "skills" / "sancho-update" / "SKILL.md",
        SKILL_TEMPLATES / "codex" / "skills" / "sancho" / "SKILL.md",
        SKILL_TEMPLATES / "codex" / "skills" / "sancho-update" / "SKILL.md",
    ]
    for path in bundled:
        assert path.exists(), f"packaged setup skill missing: {path}"
        assert "Sancho Fetch" in path.read_text(encoding="utf-8")


def test_skills_forbid_destructive_git_and_env_edits() -> None:
    for path in [
        SKILL_TEMPLATES / "claude" / "skills" / "sancho" / "SKILL.md",
        SKILL_TEMPLATES / "codex" / "skills" / "sancho" / "SKILL.md",
    ]:
        text = path.read_text(encoding="utf-8").lower()
        assert ".env" in text
        # Some variant of "don't edit / never edit / not edit" `.env`.
        assert any(phrase in text for phrase in ("not edit", "never edit", "don't edit", "do not edit"))
        # Skill should warn against editing fetched-data.
        assert "fetched-data" in text


def test_claude_md_covers_required_agent_rules() -> None:
    claude_md = ROOT / "CLAUDE.md"
    assert claude_md.exists()
    text = claude_md.read_text(encoding="utf-8")
    for must_have in (
        "sancho mode",
        "sancho paths",
        "sancho inventory",
        "sancho find sources",
        "custom/",
        "fetched-data/",
        ".env",
        "sancho update",
    ):
        assert must_have in text, f"CLAUDE.md missing {must_have}"


def test_agents_md_covers_required_agent_rules() -> None:
    agents_md = ROOT / "AGENTS.md"
    assert agents_md.exists()
    text = agents_md.read_text(encoding="utf-8")
    for must_have in (
        "sancho mode",
        "sancho paths",
        "custom/",
        "fetched-data/",
        ".env",
        "sancho update",
        "sancho repair note",
        "sancho log tail",
    ):
        assert must_have in text, f"AGENTS.md missing {must_have}"
