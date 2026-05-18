from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime

from sancho import modules
from sancho import provider_install_discovery
from sancho.cli import main
from sancho.modules import apply_updates, preview_updates


def _raise_transient_discovery_error(module_dir: Path, *, offline: bool = False) -> dict[str, str]:
    raise RuntimeError("transient discovery failure")


def test_add_provider_uses_seeded_catalog_when_live_discovery_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    monkeypatch.setattr(provider_install_discovery, "run_module_discovery", _raise_transient_discovery_error)

    assert main(["add", "fetch.bls", "--workspace", str(tmp_path), "--discover"]) == 0

    workspace = tmp_path / "sancho-workspace"
    module_dir = workspace / "source" / "fetch" / "fetch_bls"
    assert (module_dir / "catalog.json").exists()
    assert (module_dir / "catalog.meta.json").exists()

    err = capsys.readouterr().err
    assert "WARNING: Provider discovery fallback for 'fetch.bls'" in err
    assert "transient discovery failure" in err


def test_apply_updates_uses_seeded_catalog_when_live_discovery_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    monkeypatch.setattr(provider_install_discovery, "run_module_discovery", lambda module_dir, offline=False: {"ok": True})
    assert main(["add", "fetch.bls", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    managed_file = workspace / "source" / "fetch" / "fetch_bls" / "run.py"
    managed_file.write_text(managed_file.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")

    actions = preview_updates(workspace, module_id="fetch.bls")
    assert actions
    assert actions[0]["module_id"] == "fetch.bls"

    monkeypatch.setattr(provider_install_discovery, "run_module_discovery", _raise_transient_discovery_error)
    changed = apply_updates(workspace, actions)

    assert "modules.lock.yaml" in changed
    assert any(path.startswith("source/fetch/fetch_bls/") for path in changed)

    err = capsys.readouterr().err
    assert "WARNING: Provider discovery fallback for 'fetch.bls'" in err
    assert "transient discovery failure" in err


def test_add_provider_fails_when_live_discovery_fails_and_seeded_artifacts_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0

    original_copy = modules._copy_template

    def _copy_template_without_meta(template_dir: Path, target_dir: Path, overwrite: bool) -> list[Path]:
        copied = original_copy(template_dir, target_dir, overwrite)
        seeded_meta = target_dir / "catalog.meta.json"
        if seeded_meta.exists():
            seeded_meta.unlink()
        return copied

    monkeypatch.setattr(modules, "_copy_template", _copy_template_without_meta)
    monkeypatch.setattr(provider_install_discovery, "run_module_discovery", _raise_transient_discovery_error)

    result = main(["add", "fetch.bls", "--workspace", str(tmp_path), "--discover"])
    assert result == 1


def test_apply_updates_fails_when_live_discovery_fails_and_seeded_artifacts_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert main(["init", "--path", str(tmp_path), "--mode", "coder", "--yes"]) == 0
    monkeypatch.setattr(provider_install_discovery, "run_module_discovery", lambda module_dir, offline=False: {"ok": True})
    assert main(["add", "fetch.bls", "--workspace", str(tmp_path)]) == 0

    workspace = tmp_path / "sancho-workspace"
    managed_file = workspace / "source" / "fetch" / "fetch_bls" / "run.py"
    managed_file.write_text(managed_file.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    actions = preview_updates(workspace, module_id="fetch.bls")
    assert actions

    original_copy = modules._copy_template

    def _copy_template_without_meta(template_dir: Path, target_dir: Path, overwrite: bool) -> list[Path]:
        copied = original_copy(template_dir, target_dir, overwrite)
        seeded_meta = target_dir / "catalog.meta.json"
        if seeded_meta.exists():
            seeded_meta.unlink()
        return copied

    monkeypatch.setattr(modules, "_copy_template", _copy_template_without_meta)
    monkeypatch.setattr(provider_install_discovery, "run_module_discovery", _raise_transient_discovery_error)

    with pytest.raises(RuntimeError) as exc:
        apply_updates(workspace, actions)

    message = str(exc.value)
    assert "live discovery failed and seeded catalog fallback is invalid" in message
    assert "Live discovery error: RuntimeError: transient discovery failure" in message
    assert "Seeded artifact validation error:" in message
    assert "catalog.meta.json present" in message
    assert "sancho module catalog refresh fetch.bls" in message
