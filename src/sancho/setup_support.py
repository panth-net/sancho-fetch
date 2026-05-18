from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sancho.constants import TEMPLATES_ROOT

BUNDLED_CLAUDE_SKILL_SRC = TEMPLATES_ROOT / "agent_skills" / "claude" / "skills"
BUNDLED_AGENTS_SKILL_SRC = TEMPLATES_ROOT / "agent_skills" / "codex" / "skills"


@dataclass
class SetupStep:
    name: str
    status: str
    detail: str = ""
    error_code: str | None = None
    safe_retry: str | None = None
    user_action_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }
        if self.error_code:
            payload["error_code"] = self.error_code
        if self.safe_retry:
            payload["safe_retry"] = self.safe_retry
        if self.status == "fail":
            payload["user_action_required"] = self.user_action_required
        return payload


@dataclass
class SetupReport:
    steps: list[SetupStep] = field(default_factory=list)
    workspace_root: Path | None = None
    library_pointer: Path | None = None
    skills_installed: list[Path] = field(default_factory=list)
    mcp_configs_written: list[Path] = field(default_factory=list)
    claude_desktop_config_installed: Path | None = None
    ready_payload: dict[str, Any] | None = None

    def add(self, step: SetupStep) -> None:
        self.steps.append(step)

    @property
    def has_failures(self) -> bool:
        return any(step.status == "fail" for step in self.steps)


def _copy_skill_tree(src: Path, dst: Path) -> list[Path]:
    if not src.exists():
        return []
    copied: list[Path] = []
    for entry in src.iterdir():
        if not entry.is_dir():
            continue
        target = dst / entry.name
        target.mkdir(parents=True, exist_ok=True)
        for skill_file in entry.rglob("*"):
            if skill_file.is_dir():
                continue
            rel = skill_file.relative_to(entry)
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_file, out)
            copied.append(out)
    return copied


def _first_existing_skill_source(candidates: tuple[Path, ...]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def install_skills() -> tuple[SetupStep, list[Path]]:
    home = Path.home()
    claude_target = home / ".claude" / "skills"
    agents_target = home / ".agents" / "skills"
    installed: list[Path] = []
    claude_src = _first_existing_skill_source((BUNDLED_CLAUDE_SKILL_SRC,))
    agents_src = _first_existing_skill_source((BUNDLED_AGENTS_SKILL_SRC,))
    try:
        if claude_src is not None:
            installed.extend(_copy_skill_tree(claude_src, claude_target))
        if agents_src is not None:
            installed.extend(_copy_skill_tree(agents_src, agents_target))
    except Exception as exc:
        return SetupStep("skills", "warn", f"skill install failed: {exc}"), installed
    if not installed:
        return SetupStep(
            "skills",
            "warn",
            "No Claude/Codex skill files were found. The CLI is installed, but AI slash-command guidance was not installed.",
        ), installed
    return SetupStep(
        "skills",
        "ok",
        f"installed {len(installed)} file(s) to ~/.claude/skills and ~/.agents/skills",
    ), installed
