from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sancho.constants import TEMPLATES_ROOT
from sancho.utils import file_sha256

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


def _skill_manifest_path() -> Path:
    """Record of what Sancho itself wrote, kept outside the skills folders.

    Without it we cannot tell "the user customised this skill" from "this skill
    is simply from an older release" — they both just differ from the bundle.
    Lives in ~/.sancho/ so it never confuses an agent's skill loader.
    """
    return Path.home() / ".sancho" / "skill-manifest.json"


def _load_skill_manifest() -> dict[str, str]:
    path = _skill_manifest_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_skill_manifest(manifest: dict[str, str]) -> None:
    path = _skill_manifest_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        # A missing manifest only costs us edit-detection next run; never fail setup.
        pass


def _copy_skill_tree(
    src: Path,
    dst: Path,
    manifest: dict[str, str],
    skipped: list[Path],
    allow_local_edits: bool,
) -> list[Path]:
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
            key = str(out)
            recorded = manifest.get(key)
            if (
                not allow_local_edits
                and out.exists()
                and recorded is not None
                and file_sha256(out) != recorded
            ):
                skipped.append(out)
                continue
            shutil.copy2(skill_file, out)
            manifest[key] = file_sha256(out)
            copied.append(out)
    return copied


def _first_existing_skill_source(candidates: tuple[Path, ...]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def install_skills(*, allow_local_edits: bool = False) -> tuple[SetupStep, list[Path]]:
    home = Path.home()
    claude_target = home / ".claude" / "skills"
    agents_target = home / ".agents" / "skills"
    installed: list[Path] = []
    skipped: list[Path] = []
    manifest = _load_skill_manifest()
    claude_src = _first_existing_skill_source((BUNDLED_CLAUDE_SKILL_SRC,))
    agents_src = _first_existing_skill_source((BUNDLED_AGENTS_SKILL_SRC,))
    try:
        if claude_src is not None:
            installed.extend(
                _copy_skill_tree(claude_src, claude_target, manifest, skipped, allow_local_edits)
            )
        if agents_src is not None:
            installed.extend(
                _copy_skill_tree(agents_src, agents_target, manifest, skipped, allow_local_edits)
            )
    except Exception as exc:
        return SetupStep("skills", "warn", f"skill install failed: {exc}"), installed
    _save_skill_manifest(manifest)
    if not installed and not skipped:
        return SetupStep(
            "skills",
            "warn",
            "No Claude/Codex skill files were found. The CLI is installed, but AI slash-command guidance was not installed.",
        ), installed
    if skipped:
        names = ", ".join(str(path) for path in skipped[:5])
        more = f" (+{len(skipped) - 5} more)" if len(skipped) > 5 else ""
        return SetupStep(
            "skills",
            "warn",
            f"installed {len(installed)} file(s); kept your edited skill file(s): {names}{more}. "
            "Re-run with --allow-local-edits to overwrite them.",
        ), installed
    return SetupStep(
        "skills",
        "ok",
        f"installed {len(installed)} file(s) to ~/.claude/skills and ~/.agents/skills",
    ), installed
