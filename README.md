# ORCA Base Backend

ORCA is a hackathon marine decision-support backend built with FastAPI and
Python. It combines official marine data, deterministic calculations, typed
responses, and caching. It is decision support, not certified navigation
advice.

## Active architecture

The MVP is API-first and cache-assisted:

```text
Client request
    -> FastAPI and Pydantic validation
    -> source-specific cache lookup
    -> official provider on a cache miss
    -> parser and Pydantic normalization
    -> cache normalized data
    -> deterministic Python calculation
    -> typed JSON or GeoJSON response
```

The application does not require a database. The default cache is an
in-process TTL cache, so local development and tests require no external
services.

Redis is optional. Enable it only when a shared cache is useful; install the
optional dependency and run the Redis service first:

```powershell
python -m pip install -e ".[redis,test]"
docker compose up -d redis
```

Then configure:

```env
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
```

## What is currently implemented

- Versioned FastAPI routes and typed Pydantic responses.
- Shared asynchronous HTTPX infrastructure with timeouts and bounded retries.
- Deterministic demonstration sources used when optional real adapters are
  disabled; wind remains demonstration data.
- Concurrent marine-source execution with partial-failure results.
- In-memory TTL caching by default and optional Redis caching.
- An offline-tested INCOIS PFZ single-sector preview using a fresh session.
- Automatic INCOIS sector discovery and bounded concurrent sector retrieval.
- A normalized PFZ snapshot with complete/partial status and per-sector errors.
- PFZ cache-aside behavior with fresh and last-success keys, stale fallback,
  and process-local single-flight refresh protection.
- INCOIS page validation, flexible forecast-date parsing, DMS conversion, and
  malformed-row warnings.
- Deterministic nearest-valid-PFZ selection with Haversine distance, initial
  bearing, eight-point compass direction, and an embedded GeoJSON Feature.
- Optional real Copernicus Marine SST retrieval with nearest-valid-ocean-cell
  selection, Kelvin-to-Celsius conversion, and source-specific caching.
- Optional real Copernicus Marine total-wave analysis and forecast retrieval,
  including official cycle metadata and bounded coastal fallback.
- A demonstration WebSocket ingestion-progress stream.
- Separate demonstration and PFZ command-line ingestion jobs.

Current endpoints:

- `GET /v1/health`
- `GET /v1/marine/conditions?latitude=20.5&longitude=72.9`
- `GET /v1/marine/sst?latitude=18.025&longitude=70.525&at=2026-08-27T00:00:00Z`
- `GET /v1/marine/waves?latitude=18.025&longitude=70.525&at=2026-08-29T00:00:00Z`
- `GET /v1/marine/wind?latitude=18.025&longitude=70.525&at=2026-08-29T12:45:00Z`
- `GET /v1/pfz/preview?sector_code=SEC001`
- `GET /v1/pfz/snapshot`
- `GET /v1/pfz/nearest?latitude=21.6417&longitude=69.6293&at=2026-08-27T12:00:00Z`
- `WS /v1/ws/ingestion`

The nearest endpoint requires latitude and longitude. The optional `at`
parameter must include a timezone; if omitted, the current timezone-aware UTC
time is used. Source date-only validity is interpreted as complete calendar
days in Asia/Kolkata, including the final microsecond of the end date, and is
then converted to UTC.

Distance and bearing are calculated by deterministic Python code, without an
LLM or geospatial database. Distance uses the Haversine formula and the mean
Earth radius `6371.0088 km`. The full-precision distance selects the result;
rounding happens only when building the response. GeoJSON always uses
`[longitude, latitude]` coordinate order.

Example response (values are illustrative):

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
    "longitude": 68.95,
    "distance_km": 18.4,
    "bearing_deg": 141.0,
    "direction": "SE",
    "distance_from_coast_km": {"minimum": 122.0, "maximum": 127.0},
    "depth_m": {"minimum": 2.0, "maximum": 7.0}
  },
  "valid_from": "2026-08-26T18:30:00Z",
  "valid_until": "2026-08-27T18:29:59.999999Z",
  "forecast_date": "2026-08-27",
  "source": {
    "name": "INCOIS",
    "url": "https://incois.gov.in/MarineFisheries/",
    "retrieved_at": "2026-08-27T11:45:00Z"
  },
  "cache_status": "fresh",
  "completeness": "complete",
  "failed_sectors": [],
  "warnings": [],
  "geojson": {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [68.95, 22.7167]},
    "properties": {
      "sector_code": "SEC001",
      "region_name": "Gujarat",
      "landing_centre": "Lakhi Bandar",
      "distance_km": 18.4,
      "bearing_deg": 141.0,
      "direction": "SE"
    }
  },
  "notice": "Decision-support information; verify current official advisories."
}
```

Nearest-PFZ errors use the standard `{"detail":{"code","message"}}`
envelope: `404 NO_VALID_PFZ`, `502 INVALID_PFZ_RESPONSE`, and
`503 SOURCE_UNAVAILABLE`. FastAPI returns `422` for invalid coordinates or a
timezone-naive `at` value.

## Copernicus Marine SST

The optional real SST adapter uses Copernicus Marine product
`SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001`, dataset
`METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2`, and decoded `analysed_sst` values in
Kelvin. Install the pinned Toolbox integration separately from the default
application:

```powershell
python -m pip install -e ".[copernicus]"
```

Configure a local Copernicus Marine login, then set
`COPERNICUS_SST_ENABLED=true`. Never commit credentials. With the integration
disabled, `/v1/marine/conditions` continues to use the clearly labelled demo
SST source. Real waves are controlled independently, and wind remains demo.

`GET /v1/marine/sst` accepts decimal `latitude`, `longitude`, and an optional
timezone-aware `at`. It loads only a small spatial/time subset, chooses the
latest analysis not later than `at`, rejects missing and non-finite cells, and
uses deterministic Haversine distance to choose the nearest valid cell within
the configured radius. A coastal request may therefore return
`quality="nearest_valid_ocean_cell"`; it never expands the search radius.

The Toolbox returns decoded physical values. ORCA converts Kelvin to Celsius
exactly once with `Celsius = Kelvin - 273.15`. Fresh responses are cached by
dataset, variable, normalized coordinates, and requested UTC date. Matching
stale data may be returned after a provider failure, but unrelated coordinates
or dates never share an SST cache entry.

The endpoint returns a typed response containing requested and sampled
locations, sample distance, Celsius and source Kelvin values, analysis and
retrieval times, quality, source identifiers, cache status, and warnings.
Errors use the standard envelope with `404 NO_VALID_SST`,
`502 INVALID_SST_RESPONSE`, or one of `503 SST_SOURCE_UNAVAILABLE`,
`SST_AUTHENTICATION_FAILED`, and `SST_SOURCE_NOT_CONFIGURED`. Invalid
coordinates or timezone-naive timestamps return `422`.

## Copernicus Marine waves

The optional wave adapter uses product
`GLOBAL_ANALYSISFORECAST_WAV_001_027`, dataset
`cmems_mod_glo_wav_anfc_0.083deg_PT3H-i`, version `202411`, and the total
combined sea-state variables `VHM0`, `VTM02`, and `VMDR`. `VMDR` is explicitly
the direction waves come **from**. This is numerical Météo-France MFWAM model
data, not a direct observation and not a safety assessment.

Set `COPERNICUS_WAVES_ENABLED=true` after installing `.[copernicus]` and
configuring a local Copernicus Marine login. When disabled, the conditions
endpoint retains demo waves. When enabled, a failed real source is reported as
unavailable; ORCA never silently replaces it with demo data.

`GET /v1/marine/waves` accepts decimal coordinates and an optional
timezone-aware `at`. ORCA resolves and caches the latest official forecast
cycle from original-file metadata using a dry run that downloads no original
files. It then retrieves a bounded ARCO spatial/time subset with
`open_dataset()`. Analysis requests select the latest timestamp not later than
`at`; forecast requests select the first timestamp at or after `at`, subject to
the configured three-hour tolerance and ten-day product horizon.

All three Toolbox values are already decoded and are never scaled twice. A
candidate must contain finite height, period, and direction values. Selection
uses full-precision Haversine distance within the configured radius, while
response values are rounded only for presentation. Coastal land cells may
therefore fall back to `quality="nearest_valid_ocean_cell"`.

Wave cache keys include the dataset, all three variables, coordinates
normalized to six decimal places, and the requested three-hour UTC bucket.
Matching stale data can be returned after provider failure. Cycle metadata is
cached independently, and unresolved cycle metadata produces null reference
and lead fields plus an explicit warning—never fabricated forecast metadata.

Wave errors use `404 NO_VALID_WAVE_DATA`,
`404 NO_WAVE_TIME_AVAILABLE`, `502 INVALID_WAVE_RESPONSE`, and the typed 503
codes `WAVE_SOURCE_NOT_CONFIGURED`, `WAVE_AUTHENTICATION_FAILED`, and
`WAVE_SOURCE_UNAVAILABLE`. Invalid coordinates or timezone-naive timestamps
return `422`.

## Copernicus Marine wind

The optional real-wind adapter uses Level-4 near-real-time product
`WIND_GLO_PHY_L4_NRT_012_004`, dataset
`cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H`, version `202207`. It combines
scatterometer observations with bias-corrected ECMWF operational model fields.
It is an hourly blended analysis delivered daily, normally for the previous
day; it is explicitly **not** a forecast.

Set `COPERNICUS_WIND_ENABLED=true` after installing `.[copernicus]` and
configuring a saved local Copernicus Marine login. When disabled, the combined
conditions endpoint uses labelled demo wind. When enabled, a real-provider
failure is reported per source and is never replaced silently with demo wind.

`GET /v1/marine/wind` accepts decimal coordinates and an optional
timezone-aware `at`. ORCA retrieves only a bounded spatial/time subset and
selects the latest hourly timestamp not later than `at`. Future requests return
`NO_WIND_FORECAST_AVAILABLE`. ORCA applies a configurable 30-hour maximum-age
policy; this is an ORCA freshness rule, not provider metadata.

The Toolbox returns decoded `eastward_wind` and `northward_wind` values in
metres per second. ORCA never reapplies packing metadata. Speed and
meteorological direction **from** are calculated deterministically:

```text
speed_mps = sqrt(u² + v²)
direction_from_deg = (270 - degrees(atan2(v, u))) mod 360
```

Calm wind has no physical direction, so both direction value and compass are
null. Candidate selection uses full-precision Haversine distance and reports
either `exact_grid_cell` or `nearest_valid_grid_cell`. The product can contain
uncorrected model wind components over land or coastal cells, so ORCA never
claims that a finite wind cell is an ocean cell and returns an explicit source
context warning.

Wind cache keys include the dataset, both variables, coordinates normalized to
six decimals, and the requested UTC-hour bucket. Fresh, refreshed, matching
stale, and process-local single-flight behavior are supported. Stale data is
used only while it remains within the configured maximum age.

Wind errors use `404 NO_VALID_WIND_DATA`,
`404 NO_WIND_FORECAST_AVAILABLE`, `502 INVALID_WIND_RESPONSE`, and typed 503
codes `WIND_SOURCE_NOT_CONFIGURED`, `WIND_AUTHENTICATION_FAILED`,
`WIND_SOURCE_UNAVAILABLE`, and `WIND_DATA_TOO_OLD`. Invalid coordinates or a
timezone-naive timestamp return `422`.

## Setup

Python 3.11 or newer is required.

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

The default install does not include Copernicus Marine. To enable real SST,
waves, or wind, install `.[copernicus]`, configure a local Copernicus Marine
login, and use the safe settings documented in `.env.example`.

Run the API:

```powershell
fastapi dev app/main.py
```

Open the API documentation at <http://127.0.0.1:8000/docs>.

Run the complete offline test suite:

```powershell
pytest
```

Run the demonstration ingestion command:

```powershell
python -m app.jobs.ingest_demo
```

The PFZ snapshot refresh command uses the same discovery, normalization, and
cache service as the public API:

```powershell
python -m app.jobs.ingest_pfz
```

## Implementation checkpoints

### Checkpoint A — restored baseline

- Complete.
- Confirm the application starts without database configuration.
- Run the complete existing test suite.
- Protect `#sectorname` and flexible date parsing with regression tests.
- Align dependencies and documentation with the API-first architecture.

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

- D0 and D1 complete.
- Validated and integrated the Copernicus Marine global NRT L4 SST product.
- Added small-subset retrieval, temporal selection, decoded-value
  normalization, nearest-valid-ocean-cell handling, caching, and offline tests.
- Real SST replaces demo SST only when explicitly enabled; partial-failure
  behavior remains intact.
- D2-0 and D2-1 complete: the global MFWAM wave product was validated and
  integrated with typed analysis/forecast metadata, spatial fallback, caching,
  and partial-failure behavior.
- D3-0 and D3-1 complete: the global Level-4 NRT blended wind analysis was
  validated and integrated with deterministic speed/direction-from,
  maximum-age enforcement, caching, and partial-failure behavior.

### Checkpoint E — combined conditions and safety

- Add remaining priority sources.
- Run independent adapters concurrently.
- Add deterministic safety gates and reason codes.

### Checkpoint F — user interface and agents

- Connect React/MapLibre to typed JSON and GeoJSON endpoints.
- Display source, validity, freshness, and warnings.
- Add LangGraph only after deterministic services and tests are stable.

See `docs/ORCA_PROJECT_CONTEXT.md` for source rules, failure contracts, and
the complete architecture context.
