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
- Deterministic demonstration sources for SST, waves, and wind.
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
- A demonstration WebSocket ingestion-progress stream.
- Separate demonstration and PFZ command-line ingestion jobs.

Current endpoints:

- `GET /v1/health`
- `GET /v1/marine/conditions?latitude=20.5&longitude=72.9`
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

## Setup

Python 3.11 or newer is required.

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

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

- Next milestone.
- Select one authoritative source and one variable.
- Implement spatial/temporal subsetting, normalization, caching, and tests.
- Replace one demo source without breaking partial-failure behavior.

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
