from __future__ import annotations

import pytest

from sancho.provider_discovery import is_provider_module_id

pytestmark = pytest.mark.runtime


def test_is_provider_module_id_accepts_fetch_prefix_with_nested_ids() -> None:
    assert is_provider_module_id("fetch.bls") is True
    assert is_provider_module_id("fetch.census.acs_profile") is True
    assert is_provider_module_id("fetch.socrata.sf_building_permits") is True


def test_is_provider_module_id_rejects_non_fetch_or_invalid_ids() -> None:
    assert is_provider_module_id("process.normalize_records") is False
    assert is_provider_module_id("fetch") is False
    assert is_provider_module_id("fetch.") is False