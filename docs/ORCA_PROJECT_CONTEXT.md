# ORCA Project Context

## Problem

Marine information is distributed across separate platforms and formats.
Fishers and marine stakeholders need understandable, location-aware,
evidence-based information about fishing opportunities and sea conditions.

## Proposed solution

ORCA combines official marine datasets, geospatial processing,
deterministic safety logic and collaborative agents.

Core journeys:

1. Find the nearest currently valid PFZ.
2. Summarize SST, chlorophyll, weather, waves, currents and tides.
3. Produce an explainable sea-condition recommendation.
4. Compare safer routes while avoiding hazards and restricted zones.

## Technical architecture

- Frontend: React/Next.js
- Map: MapLibre GL/mapcn
- Backend: FastAPI
- Validation: Pydantic
- External requests: HTTPX
- Database: Supabase-hosted PostgreSQL
- Spatial database: PostGIS
- ORM: SQLAlchemy 2 and GeoAlchemy2
- Migrations: Alembic
- Cache: Redis
- Vector processing: GeoPandas
- NetCDF/Zarr processing: Xarray
- Agent orchestration: LangGraph
- Agent tools: LangChain-compatible typed tools
- Testing: Pytest
- Deployment: Docker

## Architectural boundaries

- Supabase hosts PostgreSQL and can provide Auth and Storage.
- SQLAlchemy remains the main FastAPI database layer.
- GeoPandas is for vector-data preparation and batch processing.
- Xarray is for SST, chlorophyll, waves and current grids.
- PostGIS handles live distances, geofences and nearest-neighbour queries.
- LLMs explain and coordinate; deterministic services calculate facts.

## Official data sources

Planned sources include:

- INCOIS PFZ
- INCOIS Ocean State Forecast
- IMD warnings and weather
- MOSDAC SST and chlorophyll
- Copernicus Marine
- Bhuvan marine and administrative boundaries

## Implemented backend foundation

The FastAPI foundation currently includes:

- Modular project structure
- Pydantic validation
- Shared asynchronous HTTPX usage
- Timeouts and retries
- Parallel marine-source execution
- Partial-source failure handling
- Memory and optional Redis caching
- WebSocket progress demonstration
- Separate ingestion commands
- SQLAlchemy/PostGIS-ready configuration
- Automated tests

## Implemented INCOIS PFZ preview

The PFZ preview currently performs:

1. Fresh-session creation.
2. `TextDataHome` bootstrap.
3. Automatic session-cookie handling.
4. Sector-page retrieval.
5. One fresh-session retry.
6. Page-marker validation.
7. Region-name parsing.
8. Forecast and validity-date parsing.
9. PFZ table extraction.
10. DMS-to-decimal conversion.
11. Malformed-row rejection.
12. Typed JSON output.

Endpoint:

    GET /v1/pfz/preview?sector_code=SEC001

## Confirmed INCOIS HTML details

Required page markers:

- `#forecastdata`
- `#satmsg`

The live region-name selector includes:

- `#sectorname`

PFZ table fields include:

- Coastal or landing location
- Direction
- Bearing
- Distance range
- Depth range
- Latitude DMS
- Longitude DMS

Important decisions:

- Never hard-code `JSESSIONID`.
- Never assume sector mappings are permanent.
- Store sector code and parsed region name separately.
- Validate mapping on every ingestion run.
- Preserve the last successful advisory when a later ingestion fails.

## Initial sectors

Initially verified:

- `SEC001`: Gujarat
- `SEC002`: Maharashtra

These mappings are observations, not permanent hard-coded rules.

The final ingestion process should discover all sector options from
`TextDataHome` and validate each sector's live region name.

## Next milestone

Implement persistent PFZ storage:

1. Configure the Supabase PostgreSQL connection.
2. Enable PostGIS.
3. Add Alembic.
4. Create data-source, dataset, ingestion-run, region, landing-centre,
   PFZ-advisory and PFZ-location tables.
5. Upsert parsed advisories transactionally.
6. Preserve previous valid data when ingestion fails.
7. Implement:

       GET /v1/pfz/nearest?latitude=...&longitude=...&at=...

8. Filter expired advisories.
9. Use PostGIS KNN for candidate selection.
10. Use `ST_Distance` with geography for displayed kilometres.
11. Return typed JSON and GeoJSON.
12. Connect the result to MapLibre.

## Safety boundary

ORCA is a decision-support prototype.

It must:

- Display official sources and validity.
- Identify stale or missing evidence.
- Avoid returning “safe” when critical evidence is unavailable.
- Never present AI-generated output as official navigation advice.