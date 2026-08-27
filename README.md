# ORCA Base Backend

This is a learning-first FastAPI foundation for the ORCA marine decision-support project. It deliberately uses deterministic demo marine sources so the complete architecture runs before official INCOIS, IMD, MOSDAC and Copernicus adapters are added.

## What already works

- FastAPI application with versioned routes
- Typed Pydantic request/response contracts
- Shared asynchronous HTTPX client
- Explicit timeouts, retries and error classification
- Parallel source execution with partial-failure handling
- In-memory caching by default and optional Redis caching
- WebSocket ingestion-progress demonstration
- Separate scheduled-ingestion command
- Supabase/PostgreSQL/PostGIS-ready SQLAlchemy configuration
- Health and marine endpoint tests

## Architecture

```text
Request -> FastAPI route -> Marine service -> Parallel source adapters
                                      |-> cache
                                      |-> later: PostgreSQL/PostGIS

Scheduled job -> same Marine service -> validated results -> later: database
WebSocket -> progress events for the frontend
```

## 1. Setup on Windows PowerShell

```powershell
cd ORCA_base_backend
py -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

## 2. Run the API

```powershell
fastapi dev app/main.py
```

Open:

- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/v1/health
- Marine conditions: http://127.0.0.1:8000/v1/marine/conditions?latitude=20.5&longitude=72.9
- Live PFZ preview: http://127.0.0.1:8000/v1/pfz/preview?sector_code=SEC001

## 3. Run tests

```powershell
pytest
```

## 4. Optional Redis/PostGIS development services

```powershell
docker compose up -d
```

Then update `.env`:

```env
REDIS_ENABLED=true
DATABASE_URL=postgresql+asyncpg://orca:orca_dev_password@localhost:5432/orca
```

For Supabase, replace `DATABASE_URL` with the SQLAlchemy-compatible connection URL from the Supabase Connect panel. Never put that URL or a Supabase secret key in the frontend.

## 5. Run the ingestion command

```powershell
python -m app.jobs.ingest_demo
```

Run the real INCOIS PFZ preview ingestion for configured sectors:

```powershell
python -m app.jobs.ingest_pfz
```

The default sectors are `SEC001,SEC002`. Change them without editing code:

```env
PFZ_SECTOR_CODES=SEC001,SEC002
PFZ_SESSION_ATTEMPTS=2
```

The PFZ implementation creates a fresh HTTP session, opens `TextDataHome`,
uses the resulting cookie for the sector request, validates `#forecastdata`
and `#satmsg`, and recreates the complete session once if the page is invalid.
No `JSESSIONID` is stored or hard-coded.

Schedule this command externally after it works manually. Do not place a recurring scheduler inside every FastAPI worker.

## Learning order

1. Read `app/clients/resilient_http.py` for HTTPX, timeouts and retries.
2. Read `app/services/marine.py` for parallel calls and partial failures.
3. Read `app/services/cache.py` for memory/Redis caching.
4. Read `app/jobs/ingest_demo.py` for scheduled-ingestion separation.
5. Read `app/api/routes/websocket.py` for live progress.
6. Replace one demo adapter with one official source adapter.

## Next ORCA implementation steps

1. Add Alembic and the first seven PFZ tables.
2. Store parsed PFZ points using PostGIS geography.
3. Replace the preview job's JSON-only output with transactional database upserts.
4. Implement `/v1/pfz/nearest` with a valid-advisory filter and PostGIS KNN.
5. Connect the GeoJSON response to MapLibre.
6. Add LangGraph only after the deterministic endpoint is tested.

This project is a decision-support prototype. It must preserve source, timestamp, validity and quality metadata and must not describe generated output as official navigation advice.
