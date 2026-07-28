from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sancho.constants import WORKSPACE_DIRNAME
from sancho.workspace import find_workspace_root


def _resolve_workspace_arg(path_arg: str) -> Path:
    return find_workspace_root(Path(path_arg).resolve())


def cmd_export(args: argparse.Namespace) -> int:
    workspace_root = _resolve_workspace_arg(args.workspace)
    output_zip = Path(args.output).resolve() if args.output else Path.cwd() / "sancho-export.zip"

    with ZipFile(output_zip, mode="w", compression=ZIP_DEFLATED) as archive:
        for file in workspace_root.rglob("*"):
            if not file.is_file():
                continue
            rel = file.relative_to(workspace_root)
            if rel.as_posix() == ".env":
                continue
            archive.write(file, arcname=Path(WORKSPACE_DIRNAME) / rel)

    print(f"Exported workspace bundle: {output_zip}")
    return 0
