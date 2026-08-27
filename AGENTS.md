# ORCA Agent Instructions

## Project purpose

ORCA is a marine decision-support platform that combines official
marine datasets, deterministic geospatial calculations and collaborative
AI agents.

Read `docs/ORCA_PROJECT_CONTEXT.md` before making architectural,
database, ingestion or agent-related changes.

## Repository structure

- `app/api/`: FastAPI routes
- `app/clients/`: external-source clients
- `app/parsers/`: pure response parsers
- `app/schemas/`: Pydantic request and response models
- `app/services/`: business logic
- `app/db/`: SQLAlchemy database layer
- `app/jobs/`: scheduled-ingestion commands
- `tests/`: automated tests and source fixtures
- `docs/`: architecture and project decisions

## Development environment

The project uses Python and a persistent virtual environment at `.venv`.

Windows activation:

    .venv\Scripts\activate

Install dependencies:

    python -m pip install -e ".[test]"

Run the API:

    fastapi dev app/main.py

Run all tests:

    pytest

API documentation:

    http://127.0.0.1:8000/docs

## Required workflow

Before modifying code:

1. Read this file.
2. Read `docs/ORCA_PROJECT_CONTEXT.md`.
3. Inspect the related implementation and tests.
4. Explain the planned change briefly.
5. Preserve unrelated existing code.

After modifying code:

1. Add or update regression tests.
2. Run the relevant tests.
3. Run the complete `pytest` suite.
4. Report which files changed.
5. Report test results and remaining limitations.

## Engineering rules

- Keep API routes thin.
- Put business logic in services.
- Keep external HTTP retrieval inside clients.
- Keep HTML, JSON and XML parsing in parser modules.
- Use Pydantic schemas for external and API data.
- Use SQLAlchemy 2 for database operations.
- Use Alembic for every schema change.
- Use PostGIS for distances and spatial queries.
- Use GeoJSON coordinate order: longitude, latitude.
- Do not let an LLM calculate distances, validity or safety thresholds.
- Do not silently invent missing marine values.
- Preserve source, retrieval time, forecast time, validity and quality metadata.
- Return controlled errors for unavailable or invalid external sources.

## INCOIS PFZ rules

- Never hard-code or store `JSESSIONID`.
- Create a fresh HTTP session for each ingestion attempt.
- Bootstrap the session through `TextDataHome`.
- Fetch sector pages using the same session.
- Retry once with a completely fresh session when page validation fails.
- Validate the presence of `#forecastdata` and `#satmsg`.
- Extract region names from the live page.
- Support `#sectorname` when extracting the region name.
- Never guess or hard-code a sector-to-region mapping.
- Store both the sector code and parsed region name.
- Treat sector mappings as changeable.
- Convert DMS coordinates to decimal coordinates.
- Reject malformed rows without rejecting all valid rows.
- Add an HTML fixture and regression test for every discovered page variation.
- Do not call INCOIS during ordinary unit tests.
- Use saved fixtures or mocked HTTP responses in tests.

## Current PFZ endpoint

Development preview:

    GET /v1/pfz/preview?sector_code=SEC001

The preview endpoint performs live retrieval and parsing but does not
yet store PFZ records in PostGIS.

The next major backend milestone is:

1. Add PFZ database tables using Alembic.
2. Store advisories and locations transactionally.
3. Implement the nearest currently valid PFZ endpoint.
4. Return JSON and GeoJSON.
5. Add PostGIS KNN and exact-distance tests.

## Security

- Never commit `.env`.
- Never expose database passwords.
- Never expose Supabase secret or service-role keys.
- Never expose external API credentials.
- Add new environment-variable names to `.env.example` without real values.
- Ask before introducing a new production dependency.

## Definition of done

A change is complete only when:

- The requested behaviour works.
- Input and external responses are validated.
- Failure cases are handled.
- Regression tests exist.
- The complete test suite passes.
- Documentation is updated when behaviour or architecture changes.