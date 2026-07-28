"""Guards against drift between duplicated operator-guidance files.

CLAUDE.md and AGENTS.md are intentionally byte-identical apart from the title
line, and the in-repo skills under .claude/skills/ and .agents/skills/ are
copies of the canonical templates so that opening this folder in Claude Code
or Codex auto-loads them with zero setup.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_SKILLS = ROOT / "src" / "sancho" / "templates" / "agent_skills"

SKILL_COPIES = [
    (".claude/skills/sancho/SKILL.md", "claude/skills/sancho/SKILL.md"),
    (".claude/skills/sancho-update/SKILL.md", "claude/skills/sancho-update/SKILL.md"),
    (".agents/skills/sancho/SKILL.md", "codex/skills/sancho/SKILL.md"),
    (".agents/skills/sancho-update/SKILL.md", "codex/skills/sancho-update/SKILL.md"),
]


def test_claude_md_matches_agents_md_after_title() -> None:
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    assert claude[1:] == agents[1:], (
        "CLAUDE.md and AGENTS.md must stay identical apart from the title line"
    )


@pytest.mark.parametrize("repo_rel, template_rel", SKILL_COPIES)
def test_repo_skills_match_templates(repo_rel: str, template_rel: str) -> None:
    repo_copy = ROOT / repo_rel
    template = TEMPLATE_SKILLS / template_rel
    assert repo_copy.exists(), f"missing in-repo skill copy: {repo_rel}"
    assert repo_copy.read_bytes() == template.read_bytes(), (
        f"{repo_rel} drifted from {template_rel}; re-copy the template"
    )
