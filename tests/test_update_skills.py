"""Phase 9 skill fixture tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_TEMPLATES = ROOT / "src" / "sancho" / "templates" / "agent_skills"


def test_claude_update_skill_exists_with_required_pieces() -> None:
    skill = SKILL_TEMPLATES / "claude" / "skills" / "sancho-update" / "SKILL.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: sancho-update" in text
    for must_have in (
        "sancho paths",
        "sancho update check",
        "sancho update preview",
        "sancho update apply",
        "rollback",
        "git pull",
        "files_with_local_edits",
        "custom_override_active",
        "backup_id",
        "sancho repair note",
    ):
        assert must_have in text, f"update skill missing reference to {must_have}"
    assert "$ARGUMENTS" in text


def test_codex_update_skill_exists_with_required_pieces() -> None:
    skill = SKILL_TEMPLATES / "codex" / "skills" / "sancho-update" / "SKILL.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: sancho-update" in text
    for must_have in (
        "AGENTS.md",
        "sancho update check",
        "sancho update preview",
        "sancho update apply",
        "rollback",
        "git pull",
        "downloaded ZIP",
    ):
        assert must_have in text


def test_update_skills_forbid_destructive_git_and_personal_path_edits() -> None:
    for path in [
        SKILL_TEMPLATES / "claude" / "skills" / "sancho-update" / "SKILL.md",
        SKILL_TEMPLATES / "codex" / "skills" / "sancho-update" / "SKILL.md",
    ]:
        text = path.read_text(encoding="utf-8").lower()
        # Forbids destructive git
        assert "never run destructive git" in text or "no `git pull`" in text or "never" in text
        assert "git pull" in text
        # Mentions the personal paths protection
        assert "fetched-data" in text
        assert ".env" in text
        assert "custom" in text
