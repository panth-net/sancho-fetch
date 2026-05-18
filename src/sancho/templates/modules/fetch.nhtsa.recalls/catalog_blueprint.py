from __future__ import annotations

from typing import Any


PROVIDER_ID = "fetch.nhtsa.recalls"
SCHEMA_VERSION = "1.0"

# NHTSA has two APIs on two different hosts:
#   vpic.nhtsa.dot.gov  -> VIN / make / model / variable metadata
#   api.nhtsa.gov       -> recalls, complaints, investigations, safety ratings
BASE_URL_VPIC = "https://vpic.nhtsa.dot.gov/api"
BASE_URL_PRODUCTS = "https://api.nhtsa.gov"
DOCS_URL = "https://vpic.nhtsa.dot.gov/api/"

VPIC_ALL_MAKES = "/vehicles/GetAllMakes"
VPIC_VARIABLE_LIST = "/vehicles/GetVehicleVariableList"
VPIC_MANUFACTURERS = "/vehicles/GetAllManufacturers"

RECALL_QUERY_PARAMS: dict[str, dict[str, Any]] = {
    "make": {"type": "string", "description": "Vehicle make", "examples": ["Ford", "Toyota"]},
    "model": {"type": "string", "description": "Vehicle model", "examples": ["F-150"]},
    "modelYear": {"type": "int", "description": "Model year", "examples": [2020, 2023]},
    "issueType": {"type": "string", "description": "Issue type", "examples": ["r (recall)", "c (complaint)", "i (investigation)"]},
}


def build_families() -> list[dict[str, Any]]:
    refs = [DOCS_URL]
    return [
        {
            "id": "recalls",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_PRODUCTS,
            "path_templates": ["/recalls/recallsByVehicle"],
            "methods": ["GET"],
            "query_params": RECALL_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Recalls for a specific vehicle. Requires make, model, modelYear.",
            "source_refs": refs,
        },
        {
            "id": "complaints",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_PRODUCTS,
            "path_templates": ["/complaints/complaintsByVehicle"],
            "methods": ["GET"],
            "query_params": RECALL_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "Consumer complaints for a specific vehicle.",
            "source_refs": refs,
        },
        {
            "id": "investigations",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_PRODUCTS,
            "path_templates": ["/investigations/investigationsByVehicle"],
            "methods": ["GET"],
            "query_params": RECALL_QUERY_PARAMS,
            "response_mode": "json",
            "envelope_key": "results",
            "description": "NHTSA investigations for a specific vehicle.",
            "source_refs": refs,
        },
        {
            "id": "vpic.vin_decode",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_VPIC,
            "path_templates": ["/vehicles/DecodeVin/{vin}", "/vehicles/DecodeVinValues/{vin}"],
            "methods": ["GET"],
            "query_params": {"format": {"type": "string", "examples": ["json"]}, "modelyear": {"type": "int"}},
            "response_mode": "json",
            "envelope_key": "Results",
            "description": "Decode a VIN into the ~144 vPIC variables (see catalog.json.vehicle_variables).",
            "source_refs": refs,
        },
        {
            "id": "vpic.meta",
            "base_aliases": ["v1"],
            "base_url": BASE_URL_VPIC,
            "path_templates": [VPIC_ALL_MAKES, VPIC_VARIABLE_LIST, VPIC_MANUFACTURERS],
            "methods": ["GET"],
            "query_params": {"format": {"type": "string", "examples": ["json"]}, "page": {"type": "int"}},
            "response_mode": "json",
            "envelope_key": "Results",
            "description": "vPIC discovery: all makes (~12k), all vPIC variables (~144), all manufacturers (~15k, paginated).",
            "source_refs": refs,
        },
    ]
