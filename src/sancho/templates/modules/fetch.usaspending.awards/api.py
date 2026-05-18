from __future__ import annotations

from typing import Any

from sancho.runtime.http import HttpClient


def fetch_dataset(
    *,
    runtime_http: dict[str, Any],
    api_token: str,
    endpoint: str,
    params: dict[str, Any],
) -> Any:
    client = HttpClient(**runtime_http)
    # USAspending v2 search endpoints use POST with JSON body.
    # Default body matches the USAspending tutorial example:
    #   - award_type_codes uses numeric codes ("10" = Grants, "A-D" = contracts)
    #   - field names are literal strings like "Award Type" (not "Contract Award Type")
    #   - sort is a plain field name; direction lives in "order"
    if "/search/" in endpoint or "/spending_by_award" in endpoint:
        if params:
            body = dict(params)
            body.setdefault("limit", 100)
        else:
            body = {
                "filters": {
                    "time_period": [{"start_date": "2024-01-01", "end_date": "2024-12-31"}],
                    "award_type_codes": ["10"],
                },
                "fields": [
                    "Award ID",
                    "Recipient Name",
                    "Start Date",
                    "End Date",
                    "Award Amount",
                    "Awarding Agency",
                    "Awarding Sub Agency",
                    "Award Type",
                    "Funding Agency",
                    "Funding Sub Agency",
                ],
                "sort": "Award Amount",
                "order": "desc",
                "limit": 100,
                "page": 1,
                "subawards": False,
            }
        return client.request_json("POST", endpoint, json_body=body)
    return client.request_json("GET", endpoint, params=params)
