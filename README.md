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
- INCOIS page validation, flexible forecast-date parsing, DMS conversion, and
  malformed-row warnings.
- A demonstration WebSocket ingestion-progress stream.
- Separate demonstration and PFZ command-line ingestion jobs.

Current endpoints:

- `GET /v1/health`
- `GET /v1/marine/conditions?latitude=20.5&longitude=72.9`
- `GET /v1/pfz/preview?sector_code=SEC001`
- `WS /v1/ws/ingestion`

Automatic PFZ sector discovery, PFZ snapshot caching, stale fallback,
nearest-PFZ calculations, GeoJSON, and real marine adapters are later
checkpoints and are not implemented yet.

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

The current single-sector PFZ preview command is:

```powershell
python -m app.jobs.ingest_pfz
```

It still uses configured development sectors. Automatic discovery replaces
that behavior in Checkpoint B.

## Implementation checkpoints

### Checkpoint A — restored baseline

- Confirm the application starts without database configuration.
- Run the complete existing test suite.
- Protect `#sectorname` and flexible date parsing with regression tests.
- Align dependencies and documentation with the API-first architecture.

### Checkpoint B — PFZ discovery and caching

- Discover every live sector from `TextDataHome`.
- Fetch all sectors with bounded concurrency.
- Normalize and cache one complete advisory snapshot.
- Add offline fixtures and regression tests.

### Checkpoint C — nearest PFZ

- Add Haversine, bearing, and compass-direction utilities.
- Add validity filtering.
- Implement `/v1/pfz/nearest`.
- Return typed JSON and GeoJSON.
- Cover fresh, refreshed, stale, 404, 502, and 503 paths.

### Checkpoint D — first real marine-condition adapter

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
