from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sancho.constants import TEMPLATES_ROOT
from sancho.install_state import (
    InstallStateError,
    atomic_write_json,
    load_install_state,
    save_install_state,
    state_lock,
)
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
        if self.status == "fail" or self.user_action_required:
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
    clients: list[dict[str, Any]] = field(default_factory=list)
    launch: dict[str, Any] | None = None
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
    except (OSError, ValueError) as exc:
        raise InstallStateError(
            f"Legacy skill ownership record is unreadable or corrupt: {path}"
        ) from exc
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        raise InstallStateError(f"Legacy skill ownership record has invalid fields: {path}")
    return data


def _save_skill_manifest(manifest: dict[str, str]) -> None:
    path = _skill_manifest_path()
    atomic_write_json(path, manifest)


def _legacy_manifest_is_proven(
    manifest: dict[str, str],
    owned_files: dict[str, Any],
) -> bool:
    path = _skill_manifest_path()
    if not path.exists():
        return True
    ownership = owned_files.get(str(path))
    current_digest = file_sha256(path)
    if isinstance(ownership, dict):
        return current_digest == ownership.get("sha256")
    # A pre-install-state manifest can be adopted only when it contains at
    # least one claim and every current skill still matches that claim.
    return bool(manifest) and all(
        Path(skill_path).is_file() and file_sha256(Path(skill_path)) == digest
        for skill_path, digest in manifest.items()
    )


def _copy_skill_tree(
    src: Path,
    dst: Path,
    owned_files: dict[str, Any],
    legacy_manifest: dict[str, str],
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
            ownership = owned_files.get(key)
            recorded = ownership.get("sha256") if isinstance(ownership, dict) else None
            current = file_sha256(out) if out.exists() else None

            # Migrate the previous valid manifest only when it still proves the
            # current file is exactly what Sancho wrote.
            legacy_digest = legacy_manifest.get(key)
            if recorded is None and current is not None and legacy_digest == current:
                recorded = current
                owned_files[key] = {"kind": "skill", "sha256": current}

            if out.exists() and recorded is None and not allow_local_edits:
                skipped.append(out)
                continue
            if out.exists() and recorded is not None and current != recorded and not allow_local_edits:
                skipped.append(out)
                continue
            shutil.copy2(skill_file, out)
            digest = file_sha256(out)
            owned_files[key] = {"kind": "skill", "sha256": digest}
            legacy_manifest[key] = digest
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
    claude_src = _first_existing_skill_source((BUNDLED_CLAUDE_SKILL_SRC,))
    agents_src = _first_existing_skill_source((BUNDLED_AGENTS_SKILL_SRC,))
    try:
        with state_lock():
            state = load_install_state()
            owned_files = state["owned_files"]
            legacy_manifest = _load_skill_manifest()
            preserve_legacy_manifest = (
                not allow_local_edits
                and not _legacy_manifest_is_proven(legacy_manifest, owned_files)
            )
            if preserve_legacy_manifest:
                legacy_manifest = {}
            if claude_src is not None:
                installed.extend(
                    _copy_skill_tree(
                        claude_src,
                        claude_target,
                        owned_files,
                        legacy_manifest,
                        skipped,
                        allow_local_edits,
                    )
                )
            if agents_src is not None:
                installed.extend(
                    _copy_skill_tree(
                        agents_src,
                        agents_target,
                        owned_files,
                        legacy_manifest,
                        skipped,
                        allow_local_edits,
                    )
                )
            if not preserve_legacy_manifest:
                _save_skill_manifest(legacy_manifest)
                owned_files[str(_skill_manifest_path())] = {
                    "kind": "legacy-skill-manifest",
                    "sha256": file_sha256(_skill_manifest_path()),
                }
            save_install_state(state)
    except InstallStateError as exc:
        return SetupStep(
            "skills",
            "fail",
            str(exc),
            error_code="ownership_state_untrusted",
            safe_retry="Repair or restore the ownership record, then rerun `sancho setup`.",
            user_action_required=True,
        ), installed
    except Exception as exc:
        return SetupStep(
            "skills",
            "fail",
            f"skill install failed safely: {exc}",
            error_code="skill_install_failed",
            safe_retry="sancho setup",
            user_action_required=False,
        ), installed
    if not installed and not skipped:
        return SetupStep(
            "skills",
            "warn",
            "No Claude/Codex skill files were found. The CLI is installed, but AI slash-command guidance was not installed.",
        ), installed
    if skipped or preserve_legacy_manifest:
        names = ", ".join(str(path) for path in skipped[:5])
        more = f" (+{len(skipped) - 5} more)" if len(skipped) > 5 else ""
        manifest_note = (
            f"; preserved unowned or edited legacy manifest {_skill_manifest_path()}"
            if preserve_legacy_manifest
            else ""
        )
        return SetupStep(
            "skills",
            "warn",
            f"installed {len(installed)} file(s); preserved unowned or edited skill file(s): "
            f"{names or 'none'}{more}{manifest_note}. Use --allow-local-edits only if you explicitly want Sancho to replace them.",
            user_action_required=True,
        ), installed
    return SetupStep(
        "skills",
        "ok",
        f"installed {len(installed)} file(s) to ~/.claude/skills and ~/.agents/skills",
    ), installed
