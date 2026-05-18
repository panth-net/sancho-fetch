from __future__ import annotations

import json

from sancho.cli import main
from sancho.module_packs import MODULE_PACKS


def test_inventory_json_lists_packs_and_providers(capsys) -> None:
    assert main(["inventory", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    pack_ids = {pack["id"] for pack in payload["packs"]}
    provider_ids = {provider["id"] for provider in payload["providers"]}

    assert set(MODULE_PACKS).issubset(pack_ids)
    assert "fetch.world_bank" in provider_ids
    assert "fetch.cdc" in provider_ids


def test_packs_and_providers_aliases(capsys) -> None:
    assert main(["packs"]) == 0
    packs_out = capsys.readouterr().out
    assert "pack.global_economic" in packs_out
    assert "fetch.world_bank" in packs_out

    assert main(["providers"]) == 0
    providers_out = capsys.readouterr().out
    assert "fetch.world_bank" in providers_out
    assert "Fetch providers:" in providers_out
