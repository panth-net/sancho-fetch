# Provider Support Matrix

> **Status: AUTHORITATIVE** - Generated from code by `scripts/generate_support_matrix.py`.
> Regenerate with: `python scripts/generate_support_matrix.py --write`

| Module | Key required | Hosted | Packs |
|---|---|---|---|
| `fetch.ahrq.meps` | None | No | `pack.health_surveys`, `pack.public_health` |
| `fetch.ahrq.nhqdr` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.ahrq.sdoh` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.airnow` | AIRNOW_API_KEY | No | `pack.environment_climate`, `pack.health_environment`, `pack.public_health` |
| `fetch.atsdr.eji` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.atsdr.svi` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.atus` | BLS_API_KEY (optional) | No | `pack.global_surveys`, `pack.health_surveys`, `pack.public_health` |
| `fetch.bea.nipa_table` | BEA_API_KEY | No | `pack.core_federal`, `pack.federal_extended`, `pack.global_economic` |
| `fetch.bls` | BLS_API_KEY (optional) | No | `pack.core_federal`, `pack.federal_extended`, `pack.global_economic`, `pack.provider_kits` |
| `fetch.brfss` | None | No | `pack.global_surveys`, `pack.health_surveys`, `pack.public_health` |
| `fetch.cdc` | SODA_API_KEY_ID (optional) | No | `pack.federal_extended`, `pack.provider_kits`, `pack.public_health` |
| `fetch.cdc.biomonitoring` | None | No | `pack.public_health` |
| `fetch.cdc.birth_defects` | None | No | `pack.public_health` |
| `fetch.cdc.heat_events` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.cdc.mmwr` | None | No | `pack.public_health` |
| `fetch.cdc.nhanes` | None | No | `pack.health_surveys`, `pack.public_health` |
| `fetch.cdc.nhis` | None | No | `pack.health_surveys`, `pack.public_health` |
| `fetch.cdc.nsfg` | None | No | `pack.health_surveys`, `pack.public_health` |
| `fetch.cdc.nvss` | None | No | `pack.public_health` |
| `fetch.cdc.nwss` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.cdc.places` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.cdc.ssun` | None | No | `pack.public_health` |
| `fetch.cdc.tracking` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.cdc.vaxview` | None | No | `pack.public_health` |
| `fetch.cdc.wisqars` | None | No | `pack.public_health` |
| `fetch.cdc.wonder` | None | No | `pack.public_health` |
| `fetch.cejst` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.census.acs_profile` | CENSUS_API_KEY | Yes | `pack.core_federal`, `pack.federal_extended`, `pack.health_equity`, `pack.public_health`, `pack.us_housing` |
| `fetch.census.cps` | None | No | `pack.health_surveys`, `pack.public_health` |
| `fetch.census.decennial` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.census.htops` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.census.onthemap_em` | None | No | `pack.public_health` |
| `fetch.census.sipp` | None | No | `pack.health_surveys`, `pack.public_health` |
| `fetch.cfpb.complaints` | None | Yes | `pack.civic_transparency`, `pack.federal_research` |
| `fetch.clinical_trials.studies` | None | Yes | `pack.federal_research`, `pack.public_health` |
| `fetch.cms.cciio` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.cms.data` | None | Yes | `pack.federal_extended`, `pack.healthcare_access`, `pack.public_health` |
| `fetch.cms.marketplace_reports` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.cms.medicaid` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.cms.synpuf` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.college_scorecard.schools` | DATA_GOV_API_KEY | Yes | `pack.federal_research` |
| `fetch.congress.bills` | CONGRESS_API_KEY | No | `pack.civic_transparency`, `pack.federal_extended` |
| `fetch.dc_open_data` | None | No | standalone |
| `fetch.doj.press_releases` | None | No | `pack.civic_transparency`, `pack.federal_research` |
| `fetch.dol.naws` | None | No | `pack.public_health` |
| `fetch.dol.osha_inspections` | DOL_API_KEY | No | `pack.federal_research` |
| `fetch.earthdata` | None | No | `pack.geospatial` |
| `fetch.earthengine` | None | No | `pack.geospatial` |
| `fetch.ed.crdc` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.eia.series` | EIA_API_KEY | No | `pack.environment_climate`, `pack.federal_extended` |
| `fetch.epa.aqs_annual` | AQS_API_KEY + AQS_EMAIL | No | `pack.environment_climate`, `pack.federal_research`, `pack.health_environment`, `pack.public_health` |
| `fetch.epa.echo_facilities` | None | No | `pack.environment_climate`, `pack.federal_research`, `pack.health_environment`, `pack.public_health` |
| `fetch.epa.ejscreen` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.epa.enviroatlas` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.epa.iris` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.epa.smart_location` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.epa.tri` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.fbi.crime` | DATA_GOV_API_KEY | No | `pack.federal_extended` |
| `fetch.fda.drug_events` | DATA_GOV_API_KEY (optional) | Yes | `pack.federal_research`, `pack.public_health` |
| `fetch.fdic.institutions` | None | Yes | `pack.federal_research` |
| `fetch.fec` | DATA_GOV_API_KEY | No | `pack.civic_transparency`, `pack.federal_research`, `pack.provider_kits` |
| `fetch.federal_register.documents` | None | Yes | `pack.civic_transparency`, `pack.federal_extended` |
| `fetch.fema.nri` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.fema.openfema` | None | Yes | `pack.environment_climate`, `pack.federal_extended` |
| `fetch.fred.series` | FRED_API_KEY | No | `pack.core_federal`, `pack.federal_extended`, `pack.global_economic` |
| `fetch.fsi` | None | No | `pack.global_governance` |
| `fetch.gpi` | None | No | `pack.global_governance` |
| `fetch.gsa_calc.ceiling_rates` | None | No | `pack.civic_transparency`, `pack.federal_research` |
| `fetch.hhs.poverty_guidelines` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.hrsa.ahrf` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.hrsa.hpsa` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.hrsa.nsch` | None | No | `pack.health_surveys`, `pack.public_health` |
| `fetch.hrsa.uds` | None | No | `pack.healthcare_access`, `pack.public_health` |
| `fetch.hud.fmr` | HUD_API_TOKEN | No | `pack.core_federal`, `pack.federal_extended`, `pack.us_housing` |
| `fetch.hud.hdx_homelessness` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.iati` | None | No | `pack.global_development` |
| `fetch.imf_cdis` | None | No | `pack.global_development` |
| `fetch.naep.adhoc_data` | None | No | `pack.federal_research`, `pack.public_health` |
| `fetch.natural_earth` | None | No | `pack.geospatial` |
| `fetch.nd_gain` | None | No | `pack.global_development` |
| `fetch.nhtsa.recalls` | None | Yes | `pack.federal_extended` |
| `fetch.nih.usrds` | None | No | `pack.health_access_helpers` |
| `fetch.nlm.vsac` | None | No | `pack.health_access_helpers` |
| `fetch.noaa.cdo` | NOAA_API_TOKEN | No | `pack.environment_climate`, `pack.federal_extended` |
| `fetch.noaa.cmra` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.noaa.nws` | None | No | `pack.health_environment`, `pack.public_health` |
| `fetch.nrel.alt_fuel_stations` | DATA_GOV_API_KEY | No | `pack.environment_climate`, `pack.federal_research` |
| `fetch.nyc_open_data` | SODA_API_KEY_ID (optional) | No | `pack.civic_socrata`, `pack.provider_kits`, `pack.us_housing` |
| `fetch.oecd_dac_crs` | None | No | `pack.global_development` |
| `fetch.oecd_sdmx` | None | No | `pack.global_development`, `pack.international_core` |
| `fetch.open_payments.datasets` | None | No | `pack.federal_research`, `pack.healthcare_access`, `pack.public_health` |
| `fetch.overture_maps` | None | No | `pack.geospatial`, `pack.global_data_hubs` |
| `fetch.owid_catalog` | None | No | `pack.global_data_hubs` |
| `fetch.owid_charts` | None | No | `pack.global_data_hubs`, `pack.international_core` |
| `fetch.pew` | None | No | `pack.global_surveys` |
| `fetch.planetary_computer` | None | No | `pack.geospatial` |
| `fetch.regulations.dockets` | DATA_GOV_API_KEY | No | `pack.civic_transparency`, `pack.federal_extended` |
| `fetch.rsf_press_freedom` | None | No | `pack.global_governance` |
| `fetch.sdg_index` | None | No | `pack.global_development` |
| `fetch.sec.company_submissions` | None | Yes | `pack.civic_transparency`, `pack.federal_research` |
| `fetch.socrata.chicago_crimes` | SODA_API_KEY_ID (optional) | No | `pack.civic_socrata` |
| `fetch.socrata.dataset` | SODA_API_KEY_ID (optional) | No | `pack.civic_socrata` |
| `fetch.socrata.la_crime` | SODA_API_KEY_ID (optional) | No | `pack.civic_socrata` |
| `fetch.socrata.seattle_building_permits` | SODA_API_KEY_ID (optional) | No | `pack.civic_socrata`, `pack.us_housing` |
| `fetch.socrata.sf_building_permits` | SODA_API_KEY_ID (optional) | No | `pack.civic_socrata`, `pack.us_housing` |
| `fetch.ti_cpi` | None | No | `pack.global_governance`, `pack.international_core` |
| `fetch.treasury.fiscal_data` | None | Yes | `pack.federal_extended`, `pack.global_economic` |
| `fetch.umich.nanda` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.un_egdi` | None | No | `pack.global_governance` |
| `fetch.undp_hdr` | None | No | `pack.global_development`, `pack.international_core` |
| `fetch.usaspending.awards` | None | Yes | `pack.civic_transparency`, `pack.federal_extended`, `pack.global_economic` |
| `fetch.usda.food_access` | None | No | `pack.health_equity`, `pack.public_health` |
| `fetch.usda.food_security` | None | No | `pack.public_health` |
| `fetch.usda.fooddata_search` | DATA_GOV_API_KEY | No | `pack.federal_research`, `pack.public_health` |
| `fetch.usda.quickstats` | USDA_NASS_API_KEY | No | `pack.federal_extended` |
| `fetch.usgs.earthquakes` | None | Yes | `pack.environment_climate`, `pack.federal_extended` |
| `fetch.uspto.application` | USPTO_API_KEY | No | `pack.federal_research` |
| `fetch.vdem` | None | No | `pack.global_governance`, `pack.international_core` |
| `fetch.wgi` | None | No | `pack.global_governance`, `pack.international_core` |
| `fetch.wjp_rule_of_law` | None | No | `pack.global_governance` |
| `fetch.world_bank` | None | Yes | `pack.federal_research`, `pack.global_economic`, `pack.international_core`, `pack.provider_kits` |
| `fetch.wvs` | None | No | `pack.global_surveys` |

**Total fetch modules:** 122
**Hosted providers:** 15
**Total packs:** 21
