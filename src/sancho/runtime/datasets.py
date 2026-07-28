from __future__ import annotations

from pathlib import Path
from typing import Any

from sancho.utils import read_yaml


class DatasetRegistry:
    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path
        self._payload: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = read_yaml(self.registry_path, default={"families": {}})
        return self._payload

    def list_families(self) -> list[str]:
        payload = self._load()
        return sorted((payload.get("families") or {}).keys())

    def list_datasets(self, family: str | None = None) -> list[dict[str, Any]]:
        payload = self._load()
        families = payload.get("families") or {}
        datasets: list[dict[str, Any]] = []
        if family:
            return list(families.get(family, []))
        for family_name, items in families.items():
            for item in items:
                enriched = dict(item)
                enriched.setdefault("family", family_name)
                datasets.append(enriched)
        return datasets
