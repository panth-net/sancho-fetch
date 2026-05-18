from __future__ import annotations


PROVIDER_ID = "fetch.census.acs_profile"
SCHEMA_VERSION = "1.0"

# Census Bureau publishes a DCAT-US /data.json listing every dataset (ACS,
# Decennial, PEP, Economic Census, etc.) with the API base path. Using this
# instead of hand-listing the 1,700+ endpoints.
BASE_URL = "https://api.census.gov"
DOCS_URL = "https://www.census.gov/data/developers/data-sets.html"
