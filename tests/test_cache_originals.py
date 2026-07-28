from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from sancho.runtime import request_state
from sancho.templates.runtime.data_store import _sanitize_segment, load_raw, save_raw


def _prov(record_dir: Path) -> dict:
    return yaml.safe_load((record_dir / "provenance.yml").read_text(encoding="utf-8"))


def test_explicit_original_bytes_are_stored_faithfully(tmp_path: Path) -> None:
    original = b"PK\x03\x04" + b"excel-workbook-bytes" * 10
    record = save_raw(
        data_raw_path=tmp_path / "fetched-data",
        module_id="fetch.ti_cpi",
        family_or_dataset_id="ti_cpi_2024",
        raw={"rows": [{"iso3": "USA", "score": 69}]},
        params={"year": 2024},
        source_url="https://example.test/cpi.xlsx",
        original_bytes=original,
        original_filename="cpi.xlsx",
        original_media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    prov = _prov(record.record_dir)
    assert prov["source_kind"] == "file"
    assert prov["original_file"] == "original.xlsx"
    assert prov["original_sha256"] == hashlib.sha256(original).hexdigest()
    stored = (record.record_dir / "original.xlsx").read_bytes()
    assert stored == original


def test_pending_original_is_auto_attached(tmp_path: Path) -> None:
    request_state.reset_run_records()
    request_state.note_pending_original(
        data=b"PAR1columnar", filename="overture.parquet", media_type=None
    )
    record = save_raw(
        data_raw_path=tmp_path / "fetched-data",
        module_id="fetch.overture",
        family_or_dataset_id="buildings",
        raw={"rows": [{"id": 1}]},
        params={"area": "boston"},
        source_url="https://example.test/buildings",
    )
    prov = _prov(record.record_dir)
    assert prov["source_kind"] == "file"
    assert prov["original_file"] == "original.parquet"
    # The pending original is consumed (not attached to a second save).
    record2 = save_raw(
        data_raw_path=tmp_path / "fetched-data",
        module_id="fetch.overture",
        family_or_dataset_id="buildings",
        raw={"rows": [{"id": 2}]},
        params={"area": "cambridge"},
        source_url="https://example.test/buildings2",
    )
    assert _prov(record2.record_dir)["source_kind"] == "api"


def test_api_record_has_no_original(tmp_path: Path) -> None:
    request_state.reset_run_records()
    record = save_raw(
        data_raw_path=tmp_path / "fetched-data",
        module_id="fetch.world_bank",
        family_or_dataset_id="v2.pop",
        raw=[{"country": "US", "value": 5}],
        params={"format": "json"},
        source_url="https://api.worldbank.org/v2/x",
    )
    prov = _prov(record.record_dir)
    assert prov["source_kind"] == "api"
    assert prov["original_file"] == ""


def test_cache_record_tail_stays_within_windows_budget(tmp_path: Path) -> None:
    # The record path *below* fetched-data (segments + key + timestamp + file)
    # must stay small enough to leave room for the workspace prefix under the
    # Windows 260-char limit. We require the tail <= 135 chars, which keeps a
    # ~125-char workspace prefix safe.
    request_state.reset_run_records()
    fetched = tmp_path / "fetched-data"
    record = save_raw(
        data_raw_path=fetched,
        module_id="m" * 80,            # absurdly long module id
        family_or_dataset_id="f" * 80,  # absurdly long family
        raw={"rows": [{"a": 1}]},
        params={"k": "v"},
        source_url="https://example.test/x",
        original_bytes=b"PAR1data",
        original_filename="huge.parquet",
    )
    deepest = max(
        (p for p in record.record_dir.iterdir() if p.is_file()),
        key=lambda p: len(str(p)),
    )
    tail = str(deepest.relative_to(fetched))
    assert len(tail) <= 135, f"cache tail too long ({len(tail)}): {tail}"


def test_long_family_segment_is_bounded() -> None:
    long_family = "x" * 300
    seg = _sanitize_segment(long_family)
    assert len(seg) <= 64
    # short values are byte-stable (historical scheme preserved)
    assert _sanitize_segment("fetch.world_bank") == "fetch.world_bank"
    assert _sanitize_segment("v2.data.country_indicator") == "v2.data.country_indicator"


def test_long_family_still_round_trips_through_cache(tmp_path: Path) -> None:
    request_state.reset_run_records()
    long_family = "really_long_dataset_family_" + "z" * 200
    save_raw(
        data_raw_path=tmp_path / "fetched-data",
        module_id="fetch.demo",
        family_or_dataset_id=long_family,
        raw=[{"a": 1}],
        params={"k": "v"},
        source_url="https://example.test/data",
    )
    # No path segment exceeds the cap.
    for path in (tmp_path / "fetched-data").rglob("*"):
        for part in path.relative_to(tmp_path / "fetched-data").parts:
            assert len(part) <= 64
    # Lookup by the same params/source still resolves the record.
    loaded = load_raw(
        data_raw_path=tmp_path / "fetched-data",
        module_id="fetch.demo",
        family_or_dataset_id=long_family,
        params={"k": "v"},
        source_url="https://example.test/data",
        max_age_seconds=3600,
    )
    assert loaded is not None
    assert loaded.raw == [{"a": 1}]
