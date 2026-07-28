"""OS-quirk hazards that break things for nontechnical users.

Covers: mac zip junk and Windows-illegal names in downloaded archives,
`.DS_Store`-style noise in file listings, `sancho env open` silently failing
on dotfiles, and GUI command strings with spaces in paths.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from sancho.path_utils import is_hidden_relpath, sanitize_zip_member
from sancho.public_output import unzip_original


def test_sanitize_zip_member_drops_mac_junk() -> None:
    assert sanitize_zip_member("__MACOSX/data/._table.csv") is None
    assert sanitize_zip_member("data/._table.csv") is None
    assert sanitize_zip_member("data/.DS_Store") is None
    assert sanitize_zip_member("Thumbs.db") is None


def test_sanitize_zip_member_repairs_windows_illegal_names() -> None:
    assert sanitize_zip_member("report: 2024.csv") == "report- 2024.csv"
    assert sanitize_zip_member("data/aux.csv") == "data/aux-file.csv"
    assert sanitize_zip_member("notes...") == "notes"
    assert sanitize_zip_member("dir\\file.txt") == "dir/file.txt"


def test_sanitize_zip_member_drops_traversal_parts() -> None:
    assert sanitize_zip_member("../../etc/passwd") == "etc/passwd"
    assert sanitize_zip_member("..") is None


def test_unzip_original_skips_junk_and_repairs_names(tmp_path: Path) -> None:
    record_dir = tmp_path / "record"
    record_dir.mkdir()
    archive = record_dir / "original.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("data/table.csv", "a,b\n1,2\n")
        zf.writestr("data/bad:name.csv", "a\n")
        zf.writestr("__MACOSX/data/._table.csv", "junk")
        zf.writestr("data/.DS_Store", "junk")
        zf.writestr("con.txt", "reserved")
    out = tmp_path / "out"
    written = unzip_original(record_dir, "original.zip", out)
    names = sorted(p.relative_to(out).as_posix() for p in written)
    assert names == ["con-file.txt", "data/bad-name.csv", "data/table.csv"]
    assert not (out / "__MACOSX").exists()


def test_is_hidden_relpath() -> None:
    assert is_hidden_relpath(".DS_Store")
    assert is_hidden_relpath("sub/.DS_Store")
    assert is_hidden_relpath(".hidden/file.txt")
    assert not is_hidden_relpath("data/file.txt")


def test_env_open_uses_text_editor_flag_on_mac(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Plain `open .env` fails (no app association) with a swallowed error;
    # the -t flag must be used so a text editor actually appears.
    from sancho import cli_env

    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    monkeypatch.setattr(cli_env.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr(
        cli_env.subprocess, "run", lambda argv, check=False: calls.append(list(argv)) or _Result()
    )
    env_file = tmp_path / ".env"
    env_file.write_text("X=1\n", encoding="utf-8")
    cli_env._open_in_editor(env_file)
    assert calls == [["open", "-t", str(env_file)]]


def test_env_open_falls_back_to_textedit_when_open_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from sancho import cli_env

    calls: list[list[str]] = []

    def fake_run(argv, check=False):
        calls.append(list(argv))

        class _Result:
            returncode = 1 if "-t" in argv else 0

        return _Result()

    monkeypatch.setattr(cli_env.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr(cli_env.subprocess, "run", fake_run)
    env_file = tmp_path / ".env"
    env_file.write_text("X=1\n", encoding="utf-8")
    cli_env._open_in_editor(env_file)
    assert calls[0][:2] == ["open", "-t"]
    assert calls[1][:2] == ["open", "-e"]


def test_chatgpt_gui_command_quotes_paths_with_spaces(tmp_path: Path) -> None:
    from sancho.mcp.config import generate_client_config

    workspace = tmp_path / "My Data" / "sancho-workspace"
    workspace.mkdir(parents=True)
    payload = generate_client_config("chatgpt-desktop", workspace)
    command = payload["gui_setup"]["command"]
    assert f'"{workspace}"' in command
