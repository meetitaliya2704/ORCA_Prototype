# ORCA Project Context

## 1. Project identity

**Name:** ORCA — Marine EcOsystem Reasoning with Collaborative Agents  
**Problem statement ID:** 26176  
**Project type:** Hackathon MVP  
**Team:** Six members  
**Primary backend:** FastAPI and Python

ORCA is a marine decision-support platform that combines official marine information, deterministic geospatial/safety calculations, caching, and later collaborative AI agents.

The intended user experience is conversational and map-based, but the backend must remain trustworthy even without an LLM.

## 2. Main MVP journeys

1. Find the nearest currently valid Potential Fishing Zone.
2. Summarize SST, chlorophyll, wind, waves, currents, tides, and weather.
3. Detect official warnings, hazards, and restricted areas.
4. Produce an explainable sea-condition recommendation.
5. Later compare candidate routes using deterministic cost and safety rules.

ORCA is decision support, not certified navigation advice.

## Current implementation status

- Checkpoints A, B, C, D0, D1, D2-0, D2-1, D3-0, D3-1, D3-2-0, D3-2-1,
  D4-0, D4-1, D5-0, and D5-1 are complete with 422 offline tests passing.
- Database dependencies and runtime components have been removed.
- Redis is an optional integration; the default cache is in memory.
- `MemoryJsonCache` enforces TTL expiration using a monotonic clock.
- A dedicated `#sectorname` regression fixture protects the live-page variant.
- Automatic PFZ sector discovery, normalized snapshot caching, stale fallback,
  and partial-sector results are implemented.
- Deterministic nearest-valid-PFZ retrieval, UTC validity normalization,
  Haversine distance, bearing, compass direction, and GeoJSON are implemented.
- Checkpoint D0 validated one real Copernicus Marine SST source, and Checkpoint
  D1 integrates it behind an optional dependency and explicit feature flag.
- Ordinary startup and tests still require neither Copernicus Marine nor
  provider credentials.
- The verified Copernicus global MFWAM total-wave analysis/forecast source is
  integrated behind a separate optional feature flag, with cycle-aware time
  selection and bounded coastal fallback.
- The verified Copernicus global Level-4 NRT blended wind analysis is integrated
  behind its own optional flag. It derives speed and meteorological direction
  from decoded components, enforces ORCA's 30-hour freshness policy, and never
  presents the source as a forecast.
- Checkpoints D3-2-0 and D3-2-1 qualify and integrate ECMWF Open Data IFS
  deterministic 10-metre wind as a separate future-forecast source. It uses
  direct ecCodes decoding, Cycle 50r1 metadata, bounded ECMWF/AWS failover,
  and field plus point caches; Copernicus remains the recent analysis source.
- Checkpoints D4-0 and D4-1 qualify and integrate Copernicus Marine daily
  Level-4 chlorophyll-a. The adapter validates live land/interpolation flag
  metadata, preserves uncertainty and per-cell provenance, bounds water-cell
  fallback to 10 km, and treats chlorophyll as supporting environmental
  evidence rather than proof of fish presence.
- Checkpoints D5-0 and D5-1 qualify and integrate Copernicus Marine SMOC
  hourly total surface currents, including static-mask water validation,
  constituent evidence, and oceanographic direction toward.

## 3. Current repository baseline

The repository was intentionally reverted to the state associated with the second generated backend ZIP. Treat the actual checked-out files and tests as authoritative, and verify them before editing.

That baseline is expected to contain most or all of the following:

- A modular FastAPI application with `/v1` routes.
- Pydantic request/response validation.
- Shared asynchronous HTTPX infrastructure.
- Configurable timeouts and bounded retries.
- Deterministic demonstration sources for SST, waves, and wind.
- Parallel source execution with partial-failure handling.
- In-memory caching and optional Redis caching.
- A demonstration WebSocket ingestion-progress endpoint.
- Separate command-line/demo ingestion jobs.
- Automated tests using fixtures and mocked HTTP responses.
- An INCOIS PFZ live-preview endpoint.

Expected existing PFZ endpoint:

```http
GET /v1/pfz/preview?sector_code=SEC001
```

The preview flow is expected to:

1. Create a fresh INCOIS session.
2. Bootstrap through `TextDataHome`.
3. Retrieve one requested sector page with the same session.
4. Validate the page.
5. Parse forecast/advisory metadata.
6. Parse valid PFZ rows and report malformed-row warnings.
7. Convert DMS coordinates to decimal degrees.
8. Return typed JSON without persistence.

Known live-page fixes that must be present or re-applied after the revert:

- Region names can appear under `#sectorname`.
- Forecast dates may appear as `27 AUG 2026`, `27-Aug-2026`, `27/08/2026`, or `2026-08-27`.
- Date extraction needs a raw-page fallback when the expected element varies.

Before new implementation, run the current test suite and inspect whether these fixes survived the revert.

## 4. Architecture decision — API-first, cache-assisted

The earlier PostgreSQL/PostGIS persistence milestone has been abandoned for the hackathon MVP because it adds unnecessary ingestion, schema, migration, and operational work.

The active architecture is:

```text
Frontend or agent
    -> FastAPI endpoint
    -> validate request with Pydantic
    -> inspect source-specific cache
    -> fetch latest official source on cache miss/expiry
    -> parse and normalize provider response
    -> cache normalized result
    -> run deterministic Python calculations
    -> return typed JSON and GeoJSON
```

### Consequences

- PostgreSQL is not required.
- PostGIS is not required.
- Supabase is not required.
- SQLAlchemy, GeoAlchemy2, and Alembic are not required by the running application.
- The application and ordinary tests must start without `DATABASE_URL`.
- Redis is optional; the default local cache is in memory.
- Small geospatial searches, such as nearest PFZ, are performed in Python.
- External providers are not called repeatedly while equivalent fresh cached data exists.

If database helper files remain from the base skeleton, they are legacy/optional and must not be imported during normal startup. Do not resume database-schema work unless the user explicitly changes the architecture again.

## 5. Target runtime workflow

### Fresh-data path

1. The frontend sends coordinates, time, and optional vessel context.
2. FastAPI validates latitude, longitude, and time.
3. The service builds a stable cache key.
4. If fresh normalized data exists, it is reused.
5. Otherwise, the relevant official adapter fetches the provider.
6. The response is parsed and normalized with Pydantic.
7. Successfully normalized data is cached.
8. Deterministic services calculate distance, bearing, validity, thresholds, or route cost.
9. FastAPI returns typed JSON/GeoJSON with source and freshness metadata.

### Provider-failure path

1. The provider request uses a timeout and bounded retry policy.
2. If it still fails, the service checks the last successful cached value.
3. If usable cached data exists, return it as `stale` with a warning and timestamps.
4. If no usable cached data exists, return HTTP 503 with `SOURCE_UNAVAILABLE`.
5. Never fabricate a value or label incomplete evidence as safe.

## 6. PFZ source behavior

### Official pages

Bootstrap page:

```text
https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en
```

Sector page pattern:

```text
https://incois.gov.in/MarineFisheries/TextData?secid=SEC001
```

`SEC001` and `SEC002` have been observed during development, but their region mappings must never be treated as permanent.

### Required refresh algorithm

1. Create a fresh asynchronous HTTP session.
2. Bootstrap `TextDataHome`.
3. Discover all current sector option values and displayed region labels.
4. Fetch sector pages using the same session/cookies.
5. Require expected live markers such as `#forecastdata` and `#satmsg`.
6. Parse the page's live region name, including `#sectorname`.
7. Parse advisory/forecast date and validity information.
8. Parse PFZ rows.
9. Convert DMS latitude/longitude to decimal degrees.
10. Reject malformed rows individually and preserve warnings.
11. If a sector page is invalid, retry that attempt once with a completely fresh session.
12. Merge valid sector results into one normalized advisory snapshot.
13. Cache the snapshot according to its validity and configured maximum TTL.

Never hard-code or persist `JSESSIONID`. Never hard-code sector-to-region mappings.

## 7. Nearest-PFZ endpoint

Implemented:

```http
GET /v1/pfz/nearest?latitude=21.6417&longitude=69.6293&at=2026-08-27T12:00:00Z
```

`at` should be optional and default to the current timezone-aware time.

### Algorithm

1. Validate latitude in `[-90, 90]` and longitude in `[-180, 180]`.
2. Load the cached normalized advisory or refresh INCOIS.
3. Exclude advisories/locations not valid at `at`.
4. Calculate Haversine distance from the user to every valid PFZ coordinate.
5. Select the minimum distance with a deterministic tie-break.
6. Calculate initial bearing and compass direction.
7. Return the result and an embedded GeoJSON Feature.

### Response fields

```json
{
  "query": {
    "latitude": 21.6417,
    "longitude": 69.6293,
    "at": "2026-08-27T12:00:00Z"
  },
  "nearest_pfz": {
    "sector_code": "SEC001",
    "region_name": "Gujarat",
    "landing_centre": "Lakhi Bandar",
    "latitude": 22.7167,
    "longitude": 68.9500,
    "distance_km": 18.4,
    "bearing_deg": 141.0,
    "direction": "SE",
    "distance_from_coast_km": {
      "minimum": 122.0,
      "maximum": 127.0
    },
    "depth_m": {
      "minimum": 2.0,
      "maximum": 7.0
    }
  },
  "valid_from": "2026-08-26T18:30:00Z",
  "valid_until": "2026-08-27T18:29:59.999999Z",
  "forecast_date": "2026-08-27",
  "source": {
    "name": "INCOIS",
    "retrieved_at": "2026-08-27T12:00:00Z",
    "url": "https://incois.gov.in/MarineFisheries/"
  },
  "cache_status": "refreshed",
  "warnings": [],
  "geojson": {
    "type": "Feature",
    "geometry": {
      "type": "Point",
      "coordinates": [68.95, 22.7167]
    },
    "properties": {
      "sector_code": "SEC001",
      "landing_centre": "Lakhi Bandar"
    }
  }
}
```

The values above illustrate the contract only. Tests must not assume live advisory values.

### Error behavior

- `422` — invalid coordinates or request parameters.
- `404 NO_VALID_PFZ` — source data exists, but no PFZ is valid for `at`.
- `502 INVALID_PFZ_RESPONSE` — a received upstream page cannot be validated or parsed and no fallback can satisfy the request.
- `503 SOURCE_UNAVAILABLE` — provider unavailable and no usable cached result exists.

## 8. Cache model

Use a source-specific cache abstraction so the implementation can switch between in-memory and Redis without changing services.

Required operations should conceptually include:

```text
get_fresh(key)
get_stale(key)
set(key, value, ttl)
delete(key)
```

Cache status returned to clients:

- `fresh`: an unexpired cached snapshot was used.
- `refreshed`: a new official response was fetched and cached.
- `stale`: the last successful snapshot was used after refresh failure.

Suggested starting policy:

| Source category | Starting policy |
| --- | --- |
| PFZ | Follow advisory validity, with configurable maximum TTL |
| Weather | Short TTL, approximately 10–15 minutes |
| Hazards/warnings | Very short TTL, approximately 5–10 minutes |
| Waves/currents | Approximately 20–30 minutes |
| SST/chlorophyll | Approximately 1–6 hours, based on provider updates |

These are configurable engineering defaults, not claims that the source publishes at exactly those intervals.

## 9. Marine data adapters

Planned source categories:

- INCOIS PFZ and Ocean State Forecast.
- IMD weather, cyclone, and warning data.
- MOSDAC/ISRO satellite products.
- Copernicus Marine SST, chlorophyll, waves, and currents.
- Bhuvan or other authoritative boundary/geofence sources.

### Implemented Copernicus Marine SST source

- Product ID: `SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001`.
- Dataset ID: `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2`.
- Variable: `analysed_sst`, decoded by the Toolbox in Kelvin.
- Optional dependency: `copernicusmarine==2.4.1` in the `copernicus` extra.
- Provider access: the synchronous official Python `open_dataset()` API runs
  through `asyncio.to_thread()` and loads only a bounded spatial/time subset.
- Time selection: latest available analysis at or before the timezone-aware
  query time, within the configured lookback.
- Spatial selection: nearest finite, non-fill cell within the configured
  radius, using deterministic Haversine distance and coordinate tie-breaks.
- Coastal behavior: when the closest requested grid cell is marked as land,
  a nearby valid ocean cell may be returned with an explicit warning.
- Units: decoded Kelvin is converted exactly once using
  `Celsius = Kelvin - 273.15`.
- Cache keys include dataset, variable, normalized requested coordinates, and
  requested UTC analysis-date bucket. Matching stale data is eligible only
  after provider failure.
- `/v1/marine/conditions` uses this real source only when
  `COPERNICUS_SST_ENABLED=true`; it never silently substitutes demo SST after
  a real-provider failure.

### Implemented Copernicus Marine wave source

- Product ID: `GLOBAL_ANALYSISFORECAST_WAV_001_027`.
- Dataset ID: `cmems_mod_glo_wav_anfc_0.083deg_PT3H-i`, version `202411`.
- Total sea-state variables: `VHM0` significant height in metres, `VTM02`
  mean period in seconds, and `VMDR` mean direction in degrees **from**.
- Data type: Météo-France MFWAM numerical-model analysis and forecast, not an
  observation and not a safety decision.
- Provider access: bounded `open_dataset()` calls execute through
  `asyncio.to_thread()`. All values are loaded and the dataset is closed in the
  worker thread. Toolbox-decoded values are never scaled twice.
- Cycle resolution: a separately injected resolver uses metadata-only
  `get(..., dry_run=True)` original-file inventory and parses the official
  reference embedded in filenames. Successful and unavailable resolutions are
  cached independently from wave samples.
- Time policy: analysis requests select the latest timestamp not later than
  the requested time; forecast requests select the first timestamp at or after
  it. The match must be within the configured three-hour tolerance, and a
  forecast cannot exceed the reference plus ten days.
- Missing cycle metadata never blocks otherwise valid wave values. Reference
  and lead fields become null, classification becomes `unknown`, and a warning
  is returned.
- Spatial policy: height, period, and direction must all be finite. The nearest
  complete cell within the bounded radius is chosen using full-precision
  Haversine distance and coordinate tie-breaks. Static bathymetry is not
  queried during normal requests.
- Cache keys include dataset, variables, normalized coordinates, and requested
  three-hour UTC bucket. Fresh, refreshed, matching stale, and process-local
  single-flight behavior are implemented.
- `/v1/marine/conditions` uses real waves only when
  `COPERNICUS_WAVES_ENABLED=true`; otherwise it retains the labelled demo wave
  source. Real-provider failure is never replaced by demo data.

### Implemented Copernicus Marine chlorophyll-a source

- Endpoint: `GET /v1/marine/chlorophyll` with decimal coordinates and an
  optional timezone-aware `at`.
- Product: `OCEANCOLOUR_GLO_BGC_L4_NRT_009_102`; dataset
  `cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D`, version
  `202311`; product DOI `10.48670/moi-00279`.
- Variables: Toolbox-decoded `CHL` in `mg/m³`, decoded nullable
  `CHL_uncertainty` in percent, and `flags`. Packing metadata is not reapplied.
- Classification: `satellite_derived_multi_sensor`, processing level `L4`,
  and `gap_filled_product=true`. Returned cells separately identify a
  multi-sensor merged satellite pixel or a space-time interpolated gap fill;
  neither is described as a direct instrument measurement.
- Flag validation pairs provider `flag_masks` and `flag_meanings` instead of
  assuming positions. Required LAND and INTERPOLATED meanings must be unique
  and consistent. LAND takes precedence and is never returned.
- Spatial policy: bounded candidates use full-precision Haversine distance and
  coordinate tie-breaks. Exact means within one metre; ordinary nearest-grid
  and nearest-valid-water fallback are distinct. The configurable 10-km
  maximum is an ORCA policy, not provider metadata.
- Time policy: select the latest daily analysis not later than `at`, reject
  future forecast requests, and enforce a configurable 72-hour ORCA freshness
  policy based on daily publication and observed delivery delay.
- Evidence policy: interpolation, uncertainty at or above the configurable
  50% ORCA threshold, or unavailable uncertainty produces degraded evidence
  and explicit warnings without discarding otherwise valid CHL.
- Cache keys use a canonical SHA-256 identity containing the complete source,
  spatial, temporal, uncertainty, and adapter-schema configuration. Matching
  stale data is used only after source unavailability and within its configured
  maximum age. Identical misses use process-local single flight.
- `/v1/marine/conditions` includes chlorophyll concurrently. Disabled mode
  retains a labelled demo source; enabled provider failures remain explicit
  and cannot erase independent SST, wave, or wind results.
- Required attribution: `Generated using CMEMS Products, production centre
  ACRI-ST`.
- Chlorophyll-a is an environmental indicator and does not independently
  confirm fish presence. No PFZ score or safety conclusion is derived in D4-1.

### Implemented Copernicus Marine total surface-current source

- Endpoint: `GET /v1/marine/currents` with decimal coordinates and an optional
  timezone-aware `at`; no depth query is exposed.
- Product `GLOBAL_ANALYSISFORECAST_PHY_001_024`; SMOC dataset
  `cmems_mod_glo_phy_anfc_merged-uv_PT1H-i`, version `202211`.
- The fixed surface level is approximately `0.494025 m`. Provider `utotal` and
  `vtotal` remain authoritative; circulation, tide, and Stokes vectors are
  nullable constituent evidence and are never fabricated.
- Direction is oceanographic direction toward. The configurable `0.001 m/s`
  calm threshold is an ORCA presentation policy.
- Static dataset `cmems_mod_glo_phy_anfc_0.083deg_static`, version `202211`,
  verifies sea/land. Nearest-valid-water fallback is bounded by a configurable
  15-km ORCA policy.
- Valid time is selected before point caching. A metadata-only resolver supplies
  reference/lead/classification only when authoritative; otherwise all three
  remain explicitly unknown/null with a warning.
- SHA-256 cache identity includes exact selected valid time and every material
  source, spatial, temporal, consistency, and schema configuration value.
- Results are numerical-model estimates, not observations or certified
  navigation instructions.

Each adapter should return a normalized structure containing:

- Source name and URL/product identifier.
- Variable name.
- Coordinates or covered area.
- Value and unit.
- Observed time and/or forecast time.
- Validity or expiry when supplied.
- Retrieval time.
- Quality flag.
- Parsing or fallback warnings.
- Cache status at the service/API layer.

Large NetCDF, Zarr, GRIB, or GeoTIFF products must not be downloaded completely for every user request. Prefer provider-supported spatial/temporal subsetting, cache the small normalized result needed for the query, and keep adapters source-specific.

### Implemented ECMWF IFS deterministic wind forecast

- Endpoint: `GET /v1/marine/wind/forecast` with required timezone-aware future
  `at`, separate from `/v1/marine/wind` recent blended analysis.
- Source: ECMWF Open Data, IFS deterministic `oper`, 0.25-degree GRIB2,
  parameters `10u` and `10v`, without authentication.
- Cycle 50r1: 00/12 cycles provide steps 0-144 every three hours and 150-360
  every six hours; 06/18 provide steps 0-144 every three hours. `scda` is not
  used. Provider metadata, rather than the wall clock, resolves completed runs.
- Retrieval selects only the two wind messages for one cycle/step. There is no
  server-side spatial subset, so the decoded field remains global.
- Direct ecCodes decoding validates GRIB edition, component identity, cycle,
  lead, valid time, regular grid, 0.25-degree increments, ordering, dimensions,
  units, and metadata-declared missing values. Temporary files are isolated and
  removed after completed provider work.
- Spatial sampling normalizes longitude to `[-180, 180)`, handles dateline
  wrapping and descending latitude, requires a finite u/v pair, and uses
  full-precision Haversine distance with coordinate tie-breaks.
- ORCA deterministically derives speed and meteorological direction-from;
  effectively calm wind has null direction and compass fields.
- The process-local field cache is bounded by TTL, LRU entry count, and bytes.
  Its canonical identity excludes mirror, allowing coordinates and ECMWF/AWS
  retrievals to reuse an equivalent field. The JSON point cache is isolated by
  cycle, step, valid time, and six-decimal coordinates.
- Source attempts use bounded client retries, validated connect/read budgets
  enforced as one hard deadline around the synchronous official client, one
  primary, and at most one fallback. Failover is restricted to transport and
  source-availability failures. Raw provider URLs, signed URLs, temporary paths,
  and exceptions are excluded from API responses.
- Responses include explicit `numerical_forecast` classification,
  reference/valid/requested times, forecast step and lead, selected mirror,
  CC BY 4.0 attribution, ECMWF's liability disclaimer, and notice of
  ORCA-derived fields. Public errors distinguish invalid/past time, horizon,
  unavailable step/source, invalid response, missing dependency, and no valid
  wind cell.
- Windows/Python 3.13 was validated with optional versions
  `ecmwf-opendata==0.3.34` and `eccodes==2.48.0`; Windows support is not claimed
  by ECMWF. The default application imports neither package.
- The maximum horizon and effectively-calm threshold are validated settings;
  the qualified default horizon remains 360 hours. Forecast uncertainty
  increases with lead time. This checkpoint adds no IMD
  warnings, safety classification, or navigation advice.

GeoPandas may be used for local vector-file operations, CRS transformation, joins, clipping, and geofence checks. It is not required for simple Haversine nearest-PFZ calculation.

## 10. Partial failure and safety behavior

Independent external sources should run concurrently. One failure must not remove successful results from other sources.

Every combined response should expose per-source state:

- `success`
- `stale`
- `unavailable`
- `invalid`

Safety rules:

- Active official warnings take precedence over favorable conditions.
- Missing required evidence produces `INSUFFICIENT_EVIDENCE`, not `SAFE`.
- Thresholds are vessel-specific where vessel details are available.
- The response must include reason codes and source evidence.
- An LLM may explain the final deterministic result but cannot override it.

## 11. Testing strategy

Ordinary tests must be deterministic and offline.

Required PFZ coverage:

- Bootstrap and same-session sector fetch.
- Automatic sector discovery.
- `#sectorname` region parsing.
- All known forecast-date formats.
- Raw-page date fallback.
- Valid DMS conversion.
- Hemisphere handling.
- Malformed-row rejection while retaining valid rows.
- Invalid-session/page retry with a fresh session.
- Cache hit and cache miss.
- Stale-cache fallback.
- Provider failure with no fallback.
- Expired-advisory exclusion.
- Nearest-distance, bearing, and direction.
- JSON and GeoJSON response contracts.

Use saved HTML fixtures for every known INCOIS page variation. Never call the live site in the normal test suite.

## 12. Current implementation roadmap

### Checkpoint A — restored baseline

- Complete.
- Confirm the application starts without database configuration.
- Run the complete existing test suite.
- Reapply/test `#sectorname` and flexible date parsing if the revert removed them.
- Update documentation to this architecture.

### Checkpoint B — PFZ discovery and caching

- Complete.
- Discover every live sector from `TextDataHome`.
- Fetch all sectors with bounded concurrency.
- Normalize and cache one complete advisory snapshot.
- Add offline fixtures and regression tests.

### Checkpoint C — nearest PFZ

- Complete.
- Add Haversine, bearing, and compass-direction utilities.
- Add validity filtering.
- Implement `/v1/pfz/nearest`.
- Return typed JSON and GeoJSON.
- Cover fresh, refreshed, stale, 404, 502, and 503 paths.

### Checkpoint D — first real marine-condition adapter

- D0 complete: authenticated point and coastal/land-mask behavior validated
  against the verified Copernicus Marine dataset.
- D1 complete: optional official Toolbox integration, typed `/v1/marine/sst`,
  nearest-valid-ocean-cell handling, cache-aside/stale behavior, and combined
  conditions integration are implemented.
- Demo SST and waves remain the defaults when their respective real adapters
  are disabled. Wind remains demo data.
- D2-0 complete: the official global MFWAM dataset, variables, cycle semantics,
  open-ocean values, and coastal missing-cell behavior were validated.
- D2-1 complete: typed `/v1/marine/waves`, official cycle resolution,
  analysis/forecast selection, bounded nearest-valid-cell behavior,
  cache-aside/stale handling, and combined-condition integration are
  implemented.
- Demo waves remain only when the real wave adapter is disabled. Wind remains
  demo data only when the real wind adapter is disabled.
- D3-0 complete: product `WIND_GLO_PHY_L4_NRT_012_004`, dataset
  `cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H` version `202207`, and decoded
  `eastward_wind`/`northward_wind` behavior were validated. The product is a
  scatterometer/model blended analysis and explicitly has no forecast.
- D3-1 complete: typed `/v1/marine/wind`,
  bounded grid selection, deterministic speed and meteorological
  direction-from, cache-aside/stale handling, 30-hour maximum-age enforcement,
  and combined-condition partial failures are implemented.
- Because wind components may contain uncorrected model values over land and
  coastal cells, quality labels refer to valid grid cells rather than ocean
  cells and responses preserve a source-context warning.
- D3-2-0 complete: ECMWF Open Data access, current Cycle 50r1 schedules, IFS
  0.25-degree wind fields, direct decoder compatibility, and mirror behavior
  were qualified.
- D3-2-1 complete: typed future wind endpoint, cycle-aware selection, direct
  ecCodes decoding, deterministic grid sampling, bounded failover, field/point
  caching, attribution, and future selection in combined conditions are
  implemented. Copernicus recent wind remains unchanged.
- D4-0 complete: the daily global Level-4 multi-sensor gap-filled chlorophyll
  product, `CHL`, uncertainty, flags, open-ocean behavior, and coastal land
  fallback were qualified through the official Toolbox.
- D4-1 complete: typed chlorophyll endpoint, strict provider flag validation,
  uncertainty-aware evidence quality, deterministic bounded spatial/time
  selection, cache-aside/stale behavior, and combined partial failure are
  implemented. No fish-presence or safety conclusion is produced.
- D5-0 complete: SMOC and depth-current candidates were qualified; SMOC was
  selected for the first fixed-surface endpoint.
- D5-1 complete: typed total-current retrieval, static-mask coastal selection,
  deterministic direction-toward, constituent integrity evidence,
  authoritative time metadata, exact-valid-time caching, and combined partial
  failure are implemented.

### Checkpoint E — combined conditions and safety

- Add remaining priority sources.
- Run independent adapters concurrently.
- Add deterministic safety gates and reason codes.

### Checkpoint F — user interface and agents

- Connect React/MapLibre to typed JSON/GeoJSON endpoints.
- Display source, validity, freshness, and warnings.
- Add LangGraph only after deterministic services and tests are stable.

## 13. Completed PFZ milestone

The next milestone is complete when:

- The backend starts with no database and no Redis.
- INCOIS sector discovery is automatic.
- The backend uses a fresh session and never hard-codes `JSESSIONID`.
- Region parsing handles `#sectorname`.
- Valid PFZ rows from every discovered sector are normalized and cached.
- `/v1/pfz/nearest` returns the nearest currently valid PFZ using deterministic Python calculations.
- The response includes source, retrieval time, validity, cache status, warnings, and GeoJSON.
- Provider failure returns stale data clearly when available, otherwise a typed error.
- All normal tests pass without internet access.

Checkpoint D5-1 completes the deterministic total surface-current adapter.
Any next source or safety checkpoint requires separate approval.
