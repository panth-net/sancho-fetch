"""Live catalog discovery for HUD USER.

Walks three HUD list endpoints:
  GET /fmr/listStates           (~56 states + territories)
  GET /fmr/listMetroAreas       (~400 FMR metro areas)
  GET /fmr/listCounties/{state} -- iterates all states

Requires HUD_API_TOKEN env var (Bearer auth). HUD's server is intermittent;
we retry with exponential backoff.
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_hud_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()
_USER_AGENT = "sancho-hud-discovery/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token() -> str:
    return os.getenv("HUD_API_TOKEN", "").strip()


def _fetch_json(path: str) -> tuple[Any, dict[str, Any]]:
    base_url = str(getattr(BLUEPRINT, "BASE_URL"))
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "Authorization": f"Bearer {_token()}",
    }
    last_status = 0
    last_exc: Exception | None = None
    # HUD's server regularly times out on first connect; retry up to 4 times.
    for attempt in range(4):
        try:
            resp = requests.get(url, timeout=60, headers=headers)
            last_status = resp.status_code
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json(), {
                "id": path,
                "url": url,
                "status": "ok",
                "http_status": last_status,
                "count": len(resp.json()) if isinstance(resp.json(), (list, dict)) else 0,
                "error": "",
                "fetched_at": _now_iso(),
            }
        except Exception as exc:
            last_exc = exc
            time.sleep(2 ** attempt)
    return None, {
        "id": path,
        "url": url,
        "status": "error",
        "http_status": last_status,
        "count": 0,
        "error": str(last_exc or "unknown"),
        "fetched_at": _now_iso(),
    }


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.hud.fmr"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")
    if not _token():
        raise RuntimeError(f"{provider_id} requires HUD_API_TOKEN env var.")

    states, states_snap = _fetch_json(str(getattr(BLUEPRINT, "META_LIST_STATES", "/fmr/listStates")))
    metros, metros_snap = _fetch_json(str(getattr(BLUEPRINT, "META_LIST_METROS", "/fmr/listMetroAreas")))

    snapshots = [states_snap, metros_snap]
    if states_snap.get("status") != "ok" or metros_snap.get("status") != "ok":
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in snapshots if s.get("status") != "ok")
        raise RuntimeError(f"HUD FMR catalog generation failed: {detail}")

    states_list = states if isinstance(states, list) else []
    metros_list = metros if isinstance(metros, list) else []

    # Per-state counties: iterate the state codes from listStates.
    counties_by_state: dict[str, list[Any]] = {}
    total_county_count = 0
    for st in states_list:
        if not isinstance(st, dict):
            continue
        state_code = st.get("state_code") or st.get("code")
        if not state_code:
            continue
        data, snap = _fetch_json(f"/fmr/listCounties/{state_code}")
        snap["id"] = f"counties.{state_code}"
        snapshots.append(snap)
        if snap.get("status") == "ok" and isinstance(data, list):
            counties_by_state[state_code] = data
            total_county_count += len(data)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "states": states_list,
        "metro_areas": metros_list,
        "counties_by_state": counties_by_state,
    }
    stats = {
        "family_count": len(families),
        "state_count": len(states_list),
        "states_count": len(states_list),
        "metro_area_count": len(metros_list),
        "metro_areas_count": len(metros_list),
        "county_count": total_county_count,
        "counties_count": total_county_count,
        "counties_states_covered": len(counties_by_state),
    }
    meta = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "stats": stats,
        "discovery": {
            "mode": "live_required",
            "sources": snapshots,
            "docs": [docs_url],
        },
    }

    (module_dir / "catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )
    (module_dir / "catalog.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8",
    )

    return {
        "provider": provider_id,
        "module_dir": str(module_dir),
        "family_count": stats["family_count"],
        "state_count": stats["state_count"],
        "metro_area_count": stats["metro_area_count"],
        "county_count": stats["county_count"],
    }
