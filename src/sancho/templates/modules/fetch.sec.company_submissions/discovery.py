"""Live catalog discovery for SEC EDGAR.

Fetches the two canonical ticker indexes:

  https://www.sec.gov/files/company_tickers.json          (~10k filer rows)
  https://www.sec.gov/files/company_tickers_exchange.json (~10k rows + exchange)

and flattens them into a single list. SEC requires a contact email in the
User-Agent header; we read it from the SEC_CONTACT_EMAIL env var.
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def _load_blueprint() -> Any:
    path = Path(__file__).with_name("catalog_blueprint.py")
    spec = importlib.util.spec_from_file_location("sancho_sec_blueprint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLUEPRINT = _load_blueprint()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user_agent() -> str:
    contact = os.getenv("SEC_CONTACT_EMAIL", "").strip() or "noreply@example.com"
    return f"sancho-sec-discovery/1.0 {contact}"


def _fetch_json(base: str, path: str) -> tuple[Any, dict[str, Any]]:
    url = f"{base.rstrip('/')}{path}"
    last_status = 0
    try:
        resp = requests.get(
            url, timeout=60,
            headers={"User-Agent": _user_agent(), "Accept": "application/json"},
        )
        last_status = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {
            "id": path,
            "url": url,
            "status": "error",
            "http_status": last_status,
            "count": 0,
            "error": str(exc),
            "fetched_at": _now_iso(),
        }
    count = len(data) if isinstance(data, (list, dict)) else 0
    return data, {
        "id": path,
        "url": url,
        "status": "ok",
        "http_status": last_status,
        "count": count,
        "error": "",
        "fetched_at": _now_iso(),
    }


def _flatten_tickers(tickers: Any) -> list[dict[str, Any]]:
    """Flatten company_tickers.json (object with "0", "1", ... keys) -> list of rows."""
    out: list[dict[str, Any]] = []
    if not isinstance(tickers, dict):
        return out
    for _key, row in tickers.items():
        if not isinstance(row, dict):
            continue
        cik = row.get("cik_str")
        if cik is None:
            continue
        out.append({
            "cik": int(cik) if isinstance(cik, (int, str)) and str(cik).isdigit() else cik,
            "cik10": f"{int(cik):010d}" if isinstance(cik, (int, str)) and str(cik).isdigit() else None,
            "ticker": row.get("ticker"),
            "title": row.get("title"),
        })
    return out


def _merge_exchange(base: list[dict[str, Any]], exchange_data: Any) -> list[dict[str, Any]]:
    """Enrich the tickers list with exchange info from company_tickers_exchange.json."""
    if not isinstance(exchange_data, dict):
        return base
    fields = exchange_data.get("fields")
    data = exchange_data.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        return base
    # Row-oriented: each entry in `data` is a list aligned with `fields`
    try:
        idx = {f: i for i, f in enumerate(fields)}
        cik_idx = idx.get("cik")
        exch_idx = idx.get("exchange")
        if cik_idx is None:
            return base
        by_cik = {int(r[cik_idx]): r for r in data if len(r) > cik_idx}
        for entry in base:
            row = by_cik.get(entry.get("cik"))
            if row and exch_idx is not None and len(row) > exch_idx:
                entry["exchange"] = row[exch_idx]
    except Exception:
        pass
    return base


def discover(*, module_dir: Path, offline: bool = False) -> dict[str, Any]:
    provider_id = str(getattr(BLUEPRINT, "PROVIDER_ID", "fetch.sec.company_submissions"))
    schema_version = str(getattr(BLUEPRINT, "SCHEMA_VERSION", "1.0"))
    docs_url = str(getattr(BLUEPRINT, "DOCS_URL", ""))
    base_static = str(getattr(BLUEPRINT, "BASE_URL_STATIC", "https://www.sec.gov"))
    tickers_path = str(getattr(BLUEPRINT, "TICKERS_URL", "/files/company_tickers.json"))
    tickers_exchange_path = str(getattr(BLUEPRINT, "TICKERS_EXCHANGE_URL", "/files/company_tickers_exchange.json"))

    if offline:
        raise RuntimeError(f"{provider_id} requires live catalog generation; offline mode is not supported.")

    tickers_raw, tickers_snap = _fetch_json(base_static, tickers_path)
    exchange_raw, exchange_snap = _fetch_json(base_static, tickers_exchange_path)

    snapshots = [tickers_snap, exchange_snap]
    failures = [s for s in snapshots if s.get("status") != "ok"]
    if failures:
        detail = "; ".join(f"{s.get('id')}: {s.get('error', 'unknown')}" for s in failures)
        raise RuntimeError(f"SEC EDGAR catalog generation failed: {detail}")

    companies = _merge_tickers_with_exchange(tickers_raw, exchange_raw)

    families = BLUEPRINT.build_families()
    catalog = {
        "provider": provider_id,
        "schema_version": schema_version,
        "generated_at": _now_iso(),
        "families": families,
        "companies": companies,
    }
    stats = {
        "family_count": len(families),
        "company_count": len(companies),
        "companies_count": len(companies),
        "companies_with_exchange": sum(1 for c in companies if c.get("exchange")),
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
        "company_count": stats["company_count"],
    }


def _merge_tickers_with_exchange(tickers: Any, exchange_data: Any) -> list[dict[str, Any]]:
    flattened = _flatten_tickers(tickers)
    return _merge_exchange(flattened, exchange_data)
