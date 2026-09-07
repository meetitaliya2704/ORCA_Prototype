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
  disabled.
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
- Optional Copernicus Marine Level-4 chlorophyll-a retrieval with validated
  land/interpolation flags, uncertainty evidence labels, and bounded water-cell
  fallback.
- Optional ECMWF Open Data IFS deterministic 10-metre wind forecasts with
  direct ecCodes decoding, bounded mirror failover, and global-field reuse.
- A demonstration WebSocket ingestion-progress stream.
- Separate demonstration and PFZ command-line ingestion jobs.

Current endpoints:

- `GET /v1/health`
- `GET /v1/marine/conditions?latitude=20.5&longitude=72.9`
- `GET /v1/marine/sst?latitude=18.025&longitude=70.525&at=2026-08-27T00:00:00Z`
- `GET /v1/marine/waves?latitude=18.025&longitude=70.525&at=2026-08-29T00:00:00Z`
- `GET /v1/marine/wind?latitude=18.025&longitude=70.525&at=2026-08-29T12:45:00Z`
- `GET /v1/marine/wind/forecast?latitude=18.025&longitude=70.525&at=2026-08-31T00:00:00Z`
- `GET /v1/marine/chlorophyll?latitude=18.025&longitude=70.525&at=2026-08-30T12:00:00Z`
- `GET /v1/marine/currents?latitude=18.025&longitude=70.525&at=2026-08-31T22:00:00Z`
- `GET /v1/marine/sea-level?latitude=18.025&longitude=70.525&at=2026-09-01T12:00:00Z`
- `GET /v1/marine/sea-level/events?latitude=18.025&longitude=70.525&hours=48&interpolate=true`
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

## Copernicus Marine chlorophyll-a

The optional chlorophyll adapter uses product
`OCEANCOLOUR_GLO_BGC_L4_NRT_009_102`, dataset
`cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D`, version
`202311`, and decoded variables `CHL`, `CHL_uncertainty`, and `flags`. Install
the existing `.[copernicus]` extra, configure a saved local Copernicus Marine
login, and set `CHLOROPHYLL_ENABLED=true`. The endpoint remains documented and
returns a typed configuration error when disabled. Combined conditions use a
clearly labelled demonstration chlorophyll source only while the real feature
is disabled; failure after enabling the real source is never replaced by demo
data.

`GET /v1/marine/chlorophyll` accepts decimal coordinates and an optional
timezone-aware `at`. This is a daily, approximately 4-km, Level-4 multi-sensor
gap-filled analysis—not a forecast and not a direct instrument measurement at
every cell. ORCA reports `satellite_derived_multi_sensor`, processing level
`L4`, and `gap_filled_product=true`. Provider flags are validated by pairing
the live `flag_masks` and `flag_meanings`: LAND is rejected, INTERPOLATED is
accepted with `space_time_interpolated_gap_fill` provenance, and an unmarked
water value is a `multi_sensor_merged_satellite_pixel`.

Selection evaluates a bounded area with full-precision Haversine distance.
`exact_grid_cell` applies only within one metre; `nearest_grid_cell` identifies
a valid ordinary grid centre; and `nearest_valid_water_cell` identifies a
fallback after the nearest grid cell is land or invalid. The configurable
10-km maximum radius is an ORCA sampling policy. The latest daily analysis not
later than `at` must satisfy ORCA's configurable 72-hour freshness policy.
Future requests are rejected because this product is not a forecast.

Toolbox-decoded values are never scaled twice. `CHL_uncertainty` is nullable.
Interpolation, uncertainty at or above the configurable 50% threshold, and
missing uncertainty produce degraded evidence with explicit warnings. The 50%
threshold is an ORCA presentation policy, not provider metadata, and high
uncertainty does not discard an otherwise valid result.

Fresh, refreshed, and eligible matching-stale results use single-flight
protection. A deterministic SHA-256 cache identity includes the product,
dataset/version, all variables, six-decimal coordinates, requested UTC date,
radius, exact-grid tolerance, freshness, uncertainty threshold, and adapter
schema version. Changed quality policy therefore cannot reuse an old result.

Errors use the standard envelope with `422 INVALID_CHLOROPHYLL_TIME`,
`404 CHLOROPHYLL_DATA_UNAVAILABLE`, `404 NO_VALID_CHLOROPHYLL_CELL`,
`502 INVALID_CHLOROPHYLL_RESPONSE`, and typed 503 codes for not configured,
missing dependency, authentication failure, and source unavailability.
Attribution is `Generated using CMEMS Products, production centre ACRI-ST`;
the product DOI is `10.48670/moi-00279`.

Satellite-derived chlorophyll-a is an environmental indicator and does not
independently confirm fish presence. ORCA is an academic decision-support
prototype, not an official fisheries, weather, or navigation service.

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

## ECMWF IFS wind forecast

`GET /v1/marine/wind/forecast` is separate from the Copernicus recent-wind
analysis endpoint. It requires decimal coordinates and a timezone-aware future
`at` value. Responses explicitly identify the data as a numerical atmospheric
forecast and expose forecast reference time, valid time, lead hours, mirror,
licence, attribution, disclaimer, derived fields, and cache status.
The explicit top-level contract includes `provider`, `selected_mirror`,
`source_classification="numerical_forecast"`, requested and sampled decimal
coordinates, `forecast_step`, `forecast_lead_hours`, and `requested_at`.

Install the optional integration with:

```powershell
pip install -e ".[ecmwf]"
python -m eccodes selfcheck
```

No ECMWF account or API key is required. The pinned optional stack is
`ecmwf-opendata==0.3.34` plus `eccodes==2.48.0`. It was validated locally on
Windows and Python 3.13, although ECMWF does not officially claim Windows
support for this decoding stack. When disabled, neither package is imported.

ORCA uses IFS Cycle 50r1 `oper` forecasts at 0.25 degrees. The 00/12 UTC cycles
provide three-hour steps through hour 144 and six-hour steps from 150 through
360. The 06/18 cycles provide three-hour steps through hour 144. The retired
`scda` stream is never used. Cycle discovery comes from provider metadata, not
the local clock; publication commonly trails cycle time and the rolling public
archive contains only recent runs.

Each request downloads only the selected `10u` and `10v` GRIB messages, but
ECMWF does not offer server-side geographic subsetting: those two messages are
global fields. ORCA decodes them directly with ecCodes, reads missing values
from GRIB metadata, and stores compact immutable fields in a bounded
process-local TTL/LRU cache. Different coordinates for the same cycle and step
reuse that field. A separate JSON point cache supports fresh, refreshed, and
strictly matching stale results. Primary `ecmwf` access has one configured
`aws` fallback by default; retries, waits, download size, and total attempts are
bounded. The official synchronous client does not expose separate HTTP phase
timeouts, so ORCA validates connect/read budgets and enforces their sum as a
hard wall-clock deadline. Mirror failover occurs only for transport or source
availability failures, never for invalid requests or malformed GRIB content.

ORCA derives speed, meteorological direction-from, compass label, point
sampling, and Haversine distance from decoded ECMWF components. Finite land or
coastal model cells are valid atmospheric forecasts and are never labelled as
ocean observations. Forecast uncertainty increases with lead time.
The calm threshold and the maximum supported 360-hour horizon are configurable;
the default calm threshold is `0.001 m/s`.

Stable forecast errors use ORCA's standard `{"detail":{"code","message"}}`
envelope. Codes include `ECMWF_FORECAST_NOT_CONFIGURED`,
`ECMWF_DEPENDENCY_MISSING`, `INVALID_FORECAST_TIME`,
`FORECAST_OUT_OF_HORIZON`, `FORECAST_STEP_UNAVAILABLE`,
`ECMWF_SOURCE_UNAVAILABLE`, `INVALID_ECMWF_RESPONSE`, and
`NO_VALID_WIND_CELL`.

ECMWF Open Data is CC BY 4.0. Responses carry the required attribution and
liability disclaimer and identify ORCA's modifications. No IMD warnings or
safety classifications are implemented, and ORCA is not official navigation
advice.

## Copernicus Marine total surface currents

`GET /v1/marine/currents` uses product
`GLOBAL_ANALYSISFORECAST_PHY_001_024`, SMOC dataset
`cmems_mod_glo_phy_anfc_merged-uv_PT1H-i` version `202211`. Enable it with
`COPERNICUS_CURRENTS_ENABLED=true` after installing `.[copernicus]`. Disabled
mode keeps the application dependency-free and supplies only clearly labelled
demo current data to the combined development endpoint.

SMOC is an hourly numerical-model surface product at the fixed shallowest
level near `0.494025 m`. ORCA uses provider `utotal`/`vtotal` as the
authoritative total surface current. The optional decomposition exposes
general circulation (`uo`/`vo`), tides (`utide`/`vtide`), and Stokes drift
(`vsdx`/`vsdy`). A missing constituent does not erase a finite provider total;
it degrades evidence and produces a warning.

Direction is oceanographic **toward** direction: 0 degrees points north and 90
degrees east. Values at or below the configurable `0.001 m/s` calm threshold
have null direction and `CALM` compass. A bounded 15-km ORCA policy uses the
official static sea mask to reject land and select the nearest valid water cell.

The ARCO service exposes valid time but not cycle/reference/lead coordinates.
ORCA uses a metadata-only resolver; unresolved metadata returns
`time_classification="unknown"` with null reference and lead rather than
guessing. Cache identities contain the exact selected provider time, source,
coordinates, mask and every material selection threshold. Matching stale data
is eligible only after source unavailability.

Responses carry Copernicus attribution and state that model currents are
decision-support estimates, not certified navigation instructions.

## Copernicus Marine sea level and estimated extrema

`GET /v1/marine/sea-level` and `GET /v1/marine/sea-level/events` use product
`GLOBAL_ANALYSISFORECAST_PHY_001_024`, dataset
`cmems_mod_glo_phy_anfc_merged-sl_PT1H-i` version `202411`. Enable them with
`COPERNICUS_TIDES_ENABLED=true` after installing `.[copernicus]`. The default
application remains dependency-free and the combined development endpoint uses
a clearly labelled demo value while the feature is disabled.

The point endpoint distinguishes numerical astronomical tide (`ocean_tide`)
from provider-produced total modelled sea level (`total_sea_level`). It exposes
the non-tidal dynamic, inverse-barometer, global-mean steric, global-mean mass,
and separate `tide_loading` components. ORCA checks the documented equation:

```text
total ≈ ocean_tide + invert_barometer + sea_surface_height
        + global_mean_steric_variation
        + global_mean_mass_volume_variation
```

`tide_loading` is intentionally excluded. A residual above the configurable
0.005-m ORCA tolerance degrades decomposition evidence without replacing the
authoritative provider total.

The events endpoint independently returns `astronomical_tide_events` and
`total_sea_level_extrema`; total extrema are not labelled tide events. It uses
padded hourly series, deterministic local extrema, and optional guarded
three-point quadratic interpolation. Even interpolated times retain an
uncertainty of at least 60 minutes.

Both endpoints use a bounded 10-km water-cell policy and align the dynamic grid
to the official static mask within 1 km. Static, dynamic field, normalized
point, metadata, stale, and event caches have separate identities. ARCO valid
time is never classified as analysis or forecast without authoritative
metadata; unresolved reference and lead remain null.

`provider_surface_level_coordinate_m` is the provider's fixed vertical grid
coordinate (approximately 0.494 m), not local water depth. `bathymetry_m`
remains the separate model sea-floor depth. Dynamic requests select the exact
intended surface coordinate, while static-mask requests independently select
their shallowest published level.

Event `hours` is an exact duration and the requested interval is inclusive:
`[start, start + hours]`. ORCA requires the nearest provider timestamp strictly
before the start and strictly after the end. Those padding samples support
boundary-extrema confirmation and interpolation but cannot themselves produce
an event outside the requested interval. The response exposes typed
`requested_window` and `provider_window` metadata, including exact timestamps,
cadence, sample count, and padding confirmation.

A separate `tides:availability:` snapshot cache (600-second default) stores
only provider timestamp metadata. It allows omitted-`at` and covered explicit
requests to resolve the exact field before the point-cache lookup without a
second network inventory call. Availability, static, field, point, stale,
cycle, and event values use separate namespaces and process-local single-flight
locks. `/v1/marine/conditions` registers only the point source; it never runs
event extraction.

Live D6-1A verification reduced the repeated omitted-`at` point request from
7.978 seconds before hardening to 0.005 seconds, with no availability refresh
or dynamic field reload. An identical explicit-time request returned fresh in
0.001 seconds. A verified exact 48-hour event window exposed 49 inclusive
interior timestamps plus one strict neighbour on each side (51 total).

These values are numerical model elevations relative to the model/geoid reference,
not chart-datum heights, tide-gauge observations, harbour tide tables, or
certified navigation information. Attribution: E.U. Copernicus Marine Service
Information.

Stable public errors include `INVALID_TIDE_TIME`, `TIDE_DATA_UNAVAILABLE`,
`TIDE_FORECAST_OUT_OF_HORIZON`, `TIDE_TIME_UNAVAILABLE`,
`TIDE_SOURCE_UNAVAILABLE`, `INVALID_TIDE_RESPONSE`, `NO_VALID_TIDE_CELL`,
`INSUFFICIENT_TIDE_SERIES`, `TIDE_SOURCE_NOT_CONFIGURED`,
`TIDE_DEPENDENCY_MISSING`, `TIDE_AUTHENTICATION_FAILED`,
`STATIC_MASK_UNAVAILABLE`, and `STATIC_GRID_ALIGNMENT_FAILED`.

## Setup

Python 3.11 or newer is required.

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

The default install does not include Copernicus Marine. To enable real SST,
waves, wind, chlorophyll, currents, or sea level, install `.[copernicus]`, configure a local Copernicus Marine
login, and use the safe settings documented in `.env.example`.

The default install also excludes ECMWF Open Data support. Install `.[ecmwf]`
and set `ECMWF_WIND_ENABLED=true` to enable the forecast-only endpoint; no
credentials are configured or required.

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
- D3-2-0 and D3-2-1 complete: ECMWF Open Data IFS deterministic wind was
  qualified and integrated as a distinct future-forecast source with direct
  GRIB decoding, Cycle 50r1 selection, bounded failover, and two-level caching.
- D4-0 and D4-1 complete: the global daily Level-4 multi-sensor chlorophyll-a
  source was qualified and integrated with strict flag-metadata validation,
  uncertainty-aware evidence quality, bounded water-cell selection,
  configuration-isolated caching, and combined-source partial failure.
- D5-0 and D5-1 complete: the hourly SMOC total surface-current source was
  qualified and integrated with static-mask water validation, authoritative
  provider totals, constituent evidence, oceanographic direction-toward,
  cycle-safe time metadata, exact-valid-time caching, and coastal fallback.
- D6-0 and D6-1 complete: the decomposed hourly model sea-level source was
  qualified and integrated with distinct point and estimated-extrema endpoints,
  static-grid water validation, guarded interpolation, and isolated caches.
- D6-1A complete: inclusive event windows now require timestamp-proven padding,
  omitted-time point requests use short-lived availability metadata, provider
  surface-coordinate terminology is explicit, and static depth requests no
  longer start below the provider range.

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

## Local performance diagnostics

Performance Checkpoint P0 adds opt-in, request-local timing without changing
normal response bodies or provider behavior. Diagnostics and the sanitized
`Server-Timing` header are disabled by default. When enabled locally, traces
separate validation, service orchestration, cache access, single-flight and
semaphore waits, provider metadata/open/load work, deterministic
normalization, response validation, serialization, and response emission.
Trace names are low-cardinality; coordinates, cache keys, provider URLs,
credentials, exception text, and local paths are never recorded.

Run one isolated cold request and one same-process warm repeat with:

```powershell
python -m app.jobs.profile_marine --latitude 18.025 --longitude 70.525 `
  --at 2026-09-01T18:00:00Z --source all `
  --mode cold --output performance-report.json
```

`cold` means newly constructed services using an isolated in-memory cache; it
does not flush Redis or remove application data. `warm` is the identical
repeat in that profiling process. Live report files are ignored by Git.

The P0 live run confirmed that remote catalogue/open/load work dominates the
cold Copernicus paths (roughly 22-62 seconds), while identical warm requests
return in about 1â€“3 ms. ECMWF's 15.2-second cold path was split across cycle
discovery, a 1.42 MB two-message GRIB download, decoding, and deterministic
global-grid selection. FastAPI validation and response work were generally
only a few milliseconds. These measurements motivate a later, separately
approved P1 snapshot/refresh design; P0 does not change refresh behavior.

Configuration:

```text
PERFORMANCE_DIAGNOSTICS_ENABLED=false
PERFORMANCE_SERVER_TIMING_ENABLED=false
PERFORMANCE_LOG_SLOW_REQUEST_MS=1000
PERFORMANCE_PROFILE_MAX_PROVIDER_CONCURRENCY=2
```

## P1A: asynchronous regional SST snapshots

P1A migrates only the real Copernicus SST point endpoint to an opt-in,
process-local regional snapshot. The default remains disabled, so existing
direct SST behavior and `/v1/marine/conditions` are unchanged. A 2-degree
logical tile is fetched once (with padding for the configured water-cell
fallback) and can then serve multiple coordinates locally.

With `MARINE_SNAPSHOTS_ENABLED=true`, `GET /v1/marine/sst` returns `200` for a
fresh or usable stale snapshot. A stale response is labelled
`stale_refreshing` and starts or reuses one background refresh. If no usable
snapshot exists, the endpoint returns a typed `202` body with code
`MARINE_DATA_REFRESH_IN_PROGRESS` and an opaque job ID. The diagnostic query
`wait_for_refresh=true` waits for that shared job without cancelling it on
timeout. Job state is available at
`GET /v1/marine/refresh/jobs/{job_id}`.

The store and refresh locks are in-process only; multi-worker coordination is
deferred. Startup warming is non-blocking and uses unique tiles parsed from
`MARINE_SNAPSHOT_PREWARM_POINTS_JSON`. The lightweight scheduler checks daily
SST refresh eligibility without downloading the same analysis on every user
request. The default CLI calls the running FastAPI server, so it warms the
same process-local store served by the routes:

```powershell
python -m app.jobs.warm_snapshots --server-url http://127.0.0.1:8000 `
  --source sst --latitude 18.025 --longitude 70.525 --wait --status
```

Snapshot identities include source/product/dataset/variable, tile and tiling
version, exact provider valid time, fallback radius, exact-cell tolerance,
lookback/time policy, decoded-Kelvin-to-Celsius policy, configuration digest,
and schema version. Regional payloads own finite decoded arrays; no remote
Xarray handle or credentials are retained. Failed and cancelled refreshes
never replace the last successful snapshot.

P1A deliberately does not migrate waves, either wind source,
currents, sea level, tide events, PFZ, or combined conditions. P1B should move
the remaining suitable sources only after source-specific cadence and field
semantics are preserved. The P0 PFZ validation failures for `SEC001` and
`SEC006` remain a separate hardening issue.

### P1A-1 refresh failure semantics

Direct and regional SST use the same lifespan-created provider instance and
validated settings. Refresh jobs contain only safe source/tile identity; they
never copy credentials, credential paths, environment data, or provider URLs.

`202 MARINE_DATA_REFRESH_IN_PROGRESS` now means a job is actually queued or
running. If no usable snapshot exists and authentication, an optional
dependency, or configuration is unavailable, the endpoint returns the mapped
SST `503` immediately and does not create another job during the 900-second
non-retryable cooldown. Transient source failures use deterministic bounded
exponential backoff, initially 30 seconds and capped at 900 seconds, with a
`Retry-After` response header.

A stale snapshot is labelled `stale_refreshing` only while a job exists. If a
failure gate blocks refresh, it remains a `200` response labelled `stale`,
preserves the successful retrieval metadata, has no refresh job ID, and states
when automatic refresh may resume. Successful refresh clears the gate and its
attempt count. A deliberate local retry can bypass only that SST tile gate:

```powershell
python -m app.jobs.warm_snapshots --source sst --latitude 18.025 `
  --longitude 70.525 --retry-failed --wait --status
```

The P1A-1 live diagnostic found identical outcomes from the shared provider:
both direct and regional calls reached `SSTAuthenticationError` because the
Toolbox authentication system could not be contacted. The fast `202` path is
verified, but successful live publication and same-tile local sampling remain
pending until local/provider authentication is available. The process-local,
single-worker limitation remains unchanged.

## P1B-1: asynchronous regional chlorophyll snapshots

P1B-1 adds a separately opt-in regional path for
`GET /v1/marine/chlorophyll`. Enable the direct source with
`CHLOROPHYLL_ENABLED=true`, snapshots with `MARINE_SNAPSHOTS_ENABLED=true`,
and chlorophyll snapshots with `CHLOROPHYLL_SNAPSHOTS_ENABLED=true`. Disabled
mode retains the D4-1 direct-provider behavior, and combined conditions remains
on its existing direct concurrent architecture.

One bounded daily field owns decoded `CHL`, nullable `CHL_uncertainty`, and
`flags` with the validated provider `flag_masks`/`flag_meanings` mapping.
Local reads call the existing D4-1 normalizer: LAND is rejected, INTERPOLATED
and missing/high uncertainty remain degraded evidence, Haversine/radius/tie
rules are unchanged, and decoded `mg/mÂ³` is never rescaled.

Fresh fields return `200` without provider work. Usable stale fields return
`stale_refreshing` only while one shared job runs, or `stale` while a failure
gate blocks retry. Missing fields return `202` only for a queued/running job.
SST and chlorophyll share the atomic store, job registry, scheduler code, and
global two-operation heavy semaphore, while namespaced configuration and
payload identities prevent cross-source reuse.

The default chlorophyll fresh/stale windows are 86,400/172,800 seconds and the
refresh eligibility check is 21,600 seconds. Startup warming is separately
flagged and non-blocking. The server-client CLI accepts `--source chlorophyll`;
explicit `--isolated` mode is ephemeral and cannot warm another process.

Snapshots remain in memory and process-local. Use one application worker until
a later distributed-store checkpoint. Chlorophyll remains an environmental
indicator and never confirms fish presence.

The P1B-1 live gate confirmed a 33.89-ms missing-tile `202`, one deduplicated
regional call, and same-tile mapping for `18.025,70.525` and `18.5,70.8`.
That provider call was still running at the bounded 90-second validation limit,
so no live snapshot was published and no second attempt was made. Live local
`200`, coastal fallback, and same-tile provider reuse remain explicitly pending.

## E1: unified marine evidence aggregation

`POST /v1/decision-support/evidence` collects requested existing evidence into
one typed bundle. It calls the PFZ, SST, chlorophyll, wave, wind, current, and
point sea-level services directly and concurrently; it does not make HTTP calls
back into ORCA and does not run sea-level event extraction. SST and chlorophyll
retain their snapshot-aware behavior, while the other sources retain their
existing cache behavior.

The request accepts decimal `latitude`/`longitude`, one optional timezone-aware
`at`, and per-source inclusion flags. When `at` is omitted, ORCA captures UTC
once and passes the same instant to every source. Present and past wind requests
use the Copernicus recent-wind analysis. Strictly future requests use ECMWF
forecast wind, with no fallback to an older recent-wind value.

Each source is labelled `available`, `degraded`, `pending`, `unavailable`, or
`not_requested`. Existing scientific provenance, quality, uncertainty, flags,
direction conventions, attribution, warnings, and notices remain inside the
typed source response. A degraded result remains usable. Source failures and
snapshot refreshes are normalized into safe typed entries, so complete,
partial, and wholly unavailable evidence bundles normally return HTTP `200`.
Invalid requests return `422`; unexpected aggregation failures remain `500`.

E1 performs aggregation only. It calculates no safety score, fishing
suitability, route recommendation, or LLM explanation. Intentionally configured
demo sources are not substituted for unavailable enabled real providers.

## E2: deterministic operational-condition assessment

`POST /v1/decision-support/assessment` evaluates request-supplied operational
limits against one E1 evidence bundle. Callers must supply at least one finite,
positive limit for significant wave height, wind speed, or total surface-current
speed. ORCA does not choose a vessel profile or invent default limits. The
response records policy `request_supplied_limits`, version `1`, and
`limit_source=request`.

Each configured rule compares the full-precision source value using
`value > limit`; equality remains within the configured limit. An optional
request-supplied `near_limit_percentage` enables the documented band from
`limit * (1 - percentage/100)` inclusive up to, but excluding, the limit. When
it is omitted, no near-limit outcome is produced. A policy change to these
comparisons, units, or band semantics requires a policy-version change.

Overall outcomes are applied without weighting: any exceeded rule produces
`LIMIT_EXCEEDED`; otherwise missing required evidence produces
`INSUFFICIENT_EVIDENCE`; otherwise a near-limit rule produces `CAUTION`; all
other configured rules produce `WITHIN_CONFIGURED_LIMITS`. The separate
evidence confidence is `NORMAL`, `DEGRADED`, or `INSUFFICIENT` and never hides
stale, pending, coastal-fallback, uncertainty, or decomposition limitations.

PFZ, SST, chlorophyll, and sea level are returned as context only. They cannot
change the operational outcome: PFZ is not proof of safe conditions,
chlorophyll does not confirm fish presence, and modelled sea level is not
chart-datum water depth. Wind direction remains meteorological direction-from;
current direction remains oceanographic direction-toward.

Official IMD and maritime-authority warning feeds are not integrated. Every
response says so explicitly and instructs callers to verify current official
advisories. `WITHIN_CONFIGURED_LIMITS` is therefore only a comparison with the
supplied limits—not a navigation approval, universal safety finding, or claim
that no warnings exist. E2 uses deterministic Python rules with no LLM,
weighted risk score, route recommendation, or provider call beyond E1.

## E3: nearest-PFZ decision-support journey

`POST /v1/decision-support/pfz-journey` provides one deterministic workflow for
a user origin and a currently valid INCOIS PFZ. The request supplies a decimal
origin, an optional timezone-aware `at`, and at least one finite positive
operational limit. ORCA supplies no default vessel profile or threshold.

The service starts origin E1 evidence collection and nearest-valid-PFZ lookup
concurrently. When a PFZ is found, it collects a separate E1 bundle at the
official PFZ coordinate. Each bundle is evaluated independently by the existing
E2 rule engine with the same request time, limits, policy version, near-limit
policy, and warning-coverage limitation. Values from the two locations are
never averaged, and E2 evaluates already-collected evidence without calling a
provider again.

Journey status uses strict precedence: PFZ refresh pending, PFZ source
unavailable, no valid PFZ, policy not configured, either location exceeding a
limit, either location lacking critical evidence, either location in a
near-limit band, then both checked locations within configured limits. PFZ
validity and fishing potential never improve the operational assessment;
chlorophyll remains an environmental indicator and does not confirm fish
presence.

Optional GeoJSON contains the origin point, official PFZ destination point, and
a straight geographic reference line. Coordinates use GeoJSON `[longitude,
latitude]` order. The line is explicitly marked non-navigable, route not
evaluated, and geofences not evaluated. It is not a route recommendation.

Expected PFZ and partial marine-source outcomes remain typed. HTTP `200` is
used for completed journey results including no-valid-PFZ and incomplete
evidence; HTTP `202` is reserved for a genuine PFZ refresh with no usable PFZ
snapshot. The current PFZ cache service has no asynchronous refresh state, so
that status is future-compatible rather than fabricated. Official warning,
route-segment, and geofence coverage remain absent. E3 uses deterministic
Python only: no LLM, route optimization, fishing guarantee, or navigation
approval is involved.

## F0: Next.js and MapLibre prototype

The real frontend foundation lives in [`frontend/`](frontend/README.md). It is
a typed Next.js App Router client for
`POST /v1/decision-support/pfz-journey`, with Zod response validation, bounded
refresh polling, TanStack Query health reporting, and a client-only MapLibre
map. The interface preserves backend journey-status terminology and the
distinction between wind direction-from and current direction-toward.

The responsive scientific dashboard uses user-supplied operational limits and
contains explicit empty, loading, pending, partial/degraded, no-PFZ,
limit-exceeded, insufficient-evidence, provider-offline, validation, and
map-failure states. Its line is labelled “Reference line — route not
evaluated.” Demonstration data is opt-in and visibly non-live.

FastAPI accepts only the explicit origins in `CORS_ALLOWED_ORIGINS`; a
wildcard, credential-bearing URL, or URL with a path/query is rejected.
Frontend environment and command details are in the frontend README. F0 adds
no LLM, authentication, database, route generation, or direct browser access
to external marine providers.
