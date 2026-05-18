from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def fetch_bea_nipa_table(
    *,
    runtime_http: dict[str, Any],
    api_key: str,
    table_name: str,
    year: str,
    frequency: str,
) -> Any:
    params = {
        "UserID": api_key,
        "method": "GetData",
        "datasetname": "NIPA",
        "TableName": table_name,
        "Year": year,
        "Frequency": frequency,
        "ResultFormat": "JSON",
    }

    client = HttpClient(**runtime_http)
    return client.request_json("GET", "https://apps.bea.gov/api/data", params=params)
