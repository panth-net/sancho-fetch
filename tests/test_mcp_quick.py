from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.mcp

from sancho.constants import REQUIRED_DIRECTORIES, REQUIRED_FILES
from sancho.mcp.quick import QUICK_PROFILE_PACKS, ensure_quick_workspace, resolve_quick_selection
from sancho.module_packs import MODULE_PACKS


def test_quick_workspace_bootstrap_idempotent_and_sync(tmp_path, monkeypatch) -> None:
    lean_modules = MODULE_PACKS["pack.global_economic"]
    registry = {module_id: object() for module_id in lean_modules}
    monkeypatch.setattr("sancho.mcp.quick.load_template_registry", lambda: registry)

    installed: set[str] = set()
    install_calls: list[str] = []

    def fake_discover(workspace_root, zone=None):
        if zone not in (None, "source"):
            return []
        return [
            SimpleNamespace(id=module_id, manifest={"type": "fetch"}, type="fetch", zone="source")
            for module_id in sorted(installed)
        ]

    def fake_install(workspace_root, module_id, channel="stable"):
        install_calls.append(module_id)
        installed.add(module_id)
        return workspace_root / "source" / "fetch" / module_id.replace(".", "_")

    monkeypatch.setattr("sancho.mcp.quick.discover_modules", fake_discover)
    monkeypatch.setattr("sancho.mcp.quick.install_module", fake_install)

    first = ensure_quick_workspace(profile="lean", quick_home=tmp_path, install_targets=True)
    workspace_root = tmp_path / "sancho-workspace"
    assert first.workspace_root == workspace_root
    assert set(first.installed_module_ids) == set(lean_modules)
    for directory in REQUIRED_DIRECTORIES:
        assert (workspace_root / directory).exists()
    for file_name in REQUIRED_FILES:
        assert (workspace_root / file_name).exists()

    install_calls.clear()
    second = ensure_quick_workspace(profile="lean", quick_home=tmp_path, install_targets=True)
    assert second.installed_module_ids == []
    assert install_calls == []

    install_calls.clear()
    synced = ensure_quick_workspace(profile="lean", quick_home=tmp_path, sync=True, install_targets=True)
    assert set(synced.installed_module_ids) == set(lean_modules)
    assert set(install_calls) == set(lean_modules)


def test_quick_profile_resolution_matches_expected_modules() -> None:
    lean = resolve_quick_selection(profile="lean", modules_csv=None)
    balanced = resolve_quick_selection(profile="balanced", modules_csv=None)
    broad = resolve_quick_selection(profile="broad", modules_csv=None)

    assert lean.profile_targets == QUICK_PROFILE_PACKS["lean"]
    assert set(lean.resolved_modules) == set(MODULE_PACKS["pack.global_economic"])

    expected_balanced: set[str] = set()
    for pack_id in QUICK_PROFILE_PACKS["balanced"]:
        expected_balanced.update(MODULE_PACKS[pack_id])
    assert set(balanced.resolved_modules) == expected_balanced

    expected_broad: set[str] = set()
    for pack_id in QUICK_PROFILE_PACKS["broad"]:
        expected_broad.update(MODULE_PACKS[pack_id])
    assert set(broad.resolved_modules) == expected_broad


def test_quick_modules_override_accepts_short_names_and_ids() -> None:
    selection = resolve_quick_selection(
        profile="lean",
        modules_csv="bls,fetch.cdc,pack.us_housing",
    )
    assert "fetch.bls" in selection.resolved_modules
    assert "fetch.cdc" in selection.resolved_modules
    assert "pack.us_housing" in selection.resolved_targets
    for module_id in MODULE_PACKS["pack.us_housing"]:
        assert module_id in selection.resolved_modules


def test_quick_modules_override_invalid_token_has_actionable_error() -> None:
    with pytest.raises(ValueError) as exc_info:
        resolve_quick_selection(profile="lean", modules_csv="worldbnk")
    message = str(exc_info.value)
    assert "Unknown --modules token 'worldbnk'" in message
    assert "Suggestions:" in message


def test_quick_modules_override_ambiguous_provider_requires_full_id() -> None:
    with pytest.raises(ValueError) as exc_info:
        resolve_quick_selection(profile="lean", modules_csv="socrata")
    assert "Ambiguous --modules token 'socrata'" in str(exc_info.value)
