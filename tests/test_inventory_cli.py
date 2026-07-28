from __future__ import annotations

import json
from pathlib import Path

from sancho.cli import main
from sancho.cli_inventory import _inventory_payload
from sancho.module_packs import MODULE_PACKS


def test_inventory_json_lists_packs_and_providers(capsys) -> None:
    assert main(["inventory", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    pack_ids = {pack["id"] for pack in payload["packs"]}
    provider_ids = {provider["id"] for provider in payload["providers"]}

    assert set(MODULE_PACKS).issubset(pack_ids)
    assert "fetch.world_bank" in provider_ids
    assert "fetch.cdc" in provider_ids
    assert "custom_modules" in payload
    assert "custom_module_count" in payload


def test_inventory_payload_lists_workspace_custom_modules(tmp_path: Path) -> None:
    workspace_root = tmp_path / "sancho-workspace"
    module_dir = workspace_root / "custom" / "fetch" / "dc_bike_lanes"
    module_dir.mkdir(parents=True)
    (module_dir / "module.yaml").write_text(
        "\n".join(
            [
                "id: fetch.custom.dc_bike_lanes",
                "version: 0.1.0",
                "type: fetch",
                "entrypoint: module.py",
                "catalog_tier: small",
                "description: Protected bike lane centerlines from the DC open data portal",
                "managed_paths:",
                "  - module.yaml",
            ]
        ),
        encoding="utf-8",
    )

    override_dir = workspace_root / "custom" / "fetch" / "world_bank"
    override_dir.mkdir(parents=True)
    (override_dir / "module.yaml").write_text(
        "\n".join(
            [
                "id: fetch.world_bank",
                "version: 0.1.0",
                "type: fetch",
                "entrypoint: module.py",
                "catalog_tier: small",
                "description: World Bank override",
                "managed_paths:",
                "  - module.yaml",
            ]
        ),
        encoding="utf-8",
    )

    payload = _inventory_payload(workspace_root)
    assert payload["custom_module_count"] == 2
    by_id = {entry["id"]: entry for entry in payload["custom_modules"]}
    assert by_id["fetch.custom.dc_bike_lanes"]["overrides_builtin"] is False
    assert by_id["fetch.world_bank"]["overrides_builtin"] is True

    providers = {provider["id"]: provider for provider in payload["providers"]}
    assert providers["fetch.world_bank"]["custom_override_active"] is True
    assert providers["fetch.cdc"]["custom_override_active"] is False

    empty = _inventory_payload(tmp_path / "nowhere")
    assert empty["custom_modules"] == []
    assert _inventory_payload()["custom_modules"] == []


def test_packs_and_providers_aliases(capsys) -> None:
    assert main(["packs"]) == 0
    packs_out = capsys.readouterr().out
    assert "pack.global_economic" in packs_out
    assert "fetch.world_bank" in packs_out

    assert main(["providers"]) == 0
    providers_out = capsys.readouterr().out
    assert "fetch.world_bank" in providers_out
    assert "Fetch providers:" in providers_out
