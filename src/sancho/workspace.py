from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from sancho.config import (
    DEFAULT_SANCHO_CONFIG,
    DEFAULT_LOCK_CONFIG,
    DEFAULT_MODULES_CONFIG,
    load_lock_config,
    write_lock_config,
    write_modules_config,
    write_workspace_config,
)
from sancho.utils import file_sha256
from sancho.constants import (
    REQUIRED_DIRECTORIES,
    RUNTIME_ROOT_TEMPLATE_FILES,
    RUNTIME_TEMPLATES_ROOT,
    WORKSPACE_DIRNAME,
    WORKSPACE_TEMPLATES_ROOT,
)


def resolve_workspace_root(path: Path, subdir: str = WORKSPACE_DIRNAME) -> Path:
    if path.name == WORKSPACE_DIRNAME:
        return path
    return path / subdir


def find_workspace_root(path: Path) -> Path:
    """Locate a ``sancho-workspace`` directory.

    Order:
    1. ``path`` itself if it's named ``sancho-workspace``.
    2. ``path / sancho-workspace``.
    3. The registered library pointer (``~/.sancho/config.yaml``).

    This lets users run ``sancho`` from any folder once they've registered
    a library -- no ``--workspace`` flag needed.
    """
    path = path.resolve()
    if path.name == WORKSPACE_DIRNAME and path.exists():
        return path
    candidate = path / WORKSPACE_DIRNAME
    if candidate.exists():
        return candidate
    try:
        from sancho.library import read_library_record
        record = read_library_record()
        if record is not None and record.primary_workspace.exists():
            return record.primary_workspace
    except Exception:
        pass
    raise FileNotFoundError(
        f"Could not find '{WORKSPACE_DIRNAME}' under {path}, and no library is "
        "registered. Run `sancho setup --path <path-to-sancho-fetch>` from "
        "the library folder, or `sancho library register <path-to-sancho-fetch>` "
        "once if you already have a workspace elsewhere."
    )


def find_workspace_root_or_none(path: Path | None = None) -> Path | None:
    """`find_workspace_root`, but None instead of raising.

    For commands that also work before setup (inventory, find sources):
    they enrich output with workspace content when one exists and fall
    back to bundled-only listings when it doesn't.
    """
    try:
        return find_workspace_root(path or Path.cwd())
    except FileNotFoundError:
        return None


def _copy_tree(
    src_root: Path,
    dst_root: Path,
    overwrite: bool = False,
    exclude_relative: set[str] | None = None,
) -> list[Path]:
    copied: list[Path] = []
    for src in src_root.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(src_root)
        # Importing sancho.templates.runtime.* from an installed package drops
        # __pycache__ dirs inside the templates; never copy those into a
        # user's workspace.
        if "__pycache__" in rel.parts or src.suffix in {".pyc", ".pyo"}:
            continue
        rel_str = rel.as_posix()
        if exclude_relative and rel_str in exclude_relative:
            continue
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and not overwrite:
            continue
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def _root_doc_checksums(workspace_root: Path) -> dict[str, str]:
    return dict(load_lock_config(workspace_root).get("root_docs") or {})


def _record_root_doc(workspace_root: Path, file_name: str, digest: str) -> None:
    lock = load_lock_config(workspace_root)
    docs = dict(lock.get("root_docs") or {})
    docs[file_name] = digest
    lock["root_docs"] = docs
    write_lock_config(workspace_root, lock)


def _install_workspace_root_templates(workspace_root: Path, overwrite: bool = False) -> list[Path]:
    copied: list[Path] = []
    for file_name in sorted(RUNTIME_ROOT_TEMPLATE_FILES):
        src = RUNTIME_TEMPLATES_ROOT / file_name
        if not src.exists():
            continue
        dst = workspace_root / file_name
        if dst.exists() and not overwrite:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        # Remember what we shipped, so a later upgrade can tell "never touched"
        # from "the user customised this".
        _record_root_doc(workspace_root, file_name, file_sha256(dst))
        copied.append(dst)
    return copied


def refresh_workspace_root_templates(
    workspace_root: Path, *, allow_local_edits: bool = False
) -> tuple[list[Path], list[Path]]:
    """Bring the bundled agent docs up to date, keeping any the user edited.

    Returns (refreshed, kept). Same contract as managed modules and skills: if
    you never touched the file you get the current release's version, otherwise
    yours stays and you are told. Without this, an upgraded workspace keeps
    agent instructions from an old release forever.
    """
    recorded = _root_doc_checksums(workspace_root)
    refreshed: list[Path] = []
    kept: list[Path] = []
    for file_name in sorted(RUNTIME_ROOT_TEMPLATE_FILES):
        src = RUNTIME_TEMPLATES_ROOT / file_name
        if not src.exists():
            continue
        dst = workspace_root / file_name
        if dst.exists():
            current = file_sha256(dst)
            if current == file_sha256(src):
                continue
            # No recorded checksum means we cannot prove it is untouched, so
            # treat it as the user's and leave it alone.
            if not allow_local_edits and recorded.get(file_name) != current:
                kept.append(dst)
                continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        _record_root_doc(workspace_root, file_name, file_sha256(dst))
        refreshed.append(dst)
    return refreshed, kept


def initialize_workspace(
    base_path: Path,
    subdir: str,
    mode: str,
    *,
    allow_identity_migration: bool = True,
) -> Path:
    workspace_root = resolve_workspace_root(base_path.resolve(), subdir=subdir)
    # Validate an existing identity before writing anything. The CLI is the
    # designated legacy-workspace migrator; packaged extension runtimes pass
    # allow_identity_migration=False and refuse an unmarked existing workspace.
    from sancho.install_state import read_workspace_identity, workspace_identity_path

    identity_path = workspace_identity_path(workspace_root)
    if identity_path.exists():
        read_workspace_identity(workspace_root)
    elif workspace_root.exists() and any(workspace_root.iterdir()) and not allow_identity_migration:
        raise RuntimeError(
            "This existing workspace predates persistent workspace identity. "
            "Run the matching Sancho CLI setup once to migrate it before using the extension."
        )
    workspace_root.mkdir(parents=True, exist_ok=True)

    for directory in REQUIRED_DIRECTORIES:
        (workspace_root / directory).mkdir(parents=True, exist_ok=True)

    env_example_src = WORKSPACE_TEMPLATES_ROOT / ".env.example"
    env_example_dst = workspace_root / ".env.example"
    if env_example_src.exists() and not env_example_dst.exists():
        shutil.copy2(env_example_src, env_example_dst)

    if not (workspace_root / ".env").exists():
        (workspace_root / ".env").write_text((workspace_root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")

    if not (workspace_root / "sancho.yaml").exists():
        payload = DEFAULT_SANCHO_CONFIG.copy()
        payload["mode"] = mode
        write_workspace_config(workspace_root, payload)

    if not (workspace_root / "modules.yaml").exists():
        write_modules_config(workspace_root, DEFAULT_MODULES_CONFIG.copy())

    if not (workspace_root / "modules.lock.yaml").exists():
        write_lock_config(workspace_root, DEFAULT_LOCK_CONFIG.copy())

    install_runtime_templates(workspace_root, overwrite=False)
    _install_workspace_root_templates(workspace_root, overwrite=False)
    # A persistent ID distinguishes a moved workspace from an unrelated folder
    # with the same name and lets setup/uninstall prove what they are targeting.
    from sancho.install_state import ensure_workspace_identity

    ensure_workspace_identity(workspace_root)
    return workspace_root


def install_runtime_templates(workspace_root: Path, overwrite: bool = False) -> list[Path]:
    runtime_root = workspace_root / "source" / "_runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    return _copy_tree(
        RUNTIME_TEMPLATES_ROOT,
        runtime_root,
        overwrite=overwrite,
        exclude_relative=set(RUNTIME_ROOT_TEMPLATE_FILES),
    )


def list_workspace_files(root: Path) -> Iterable[Path]:
    for file in root.rglob("*"):
        if file.is_file():
            yield file
