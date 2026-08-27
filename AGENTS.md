# AGENTS.md — ORCA Backend

## 1. Required reading

Before inspecting, planning, or modifying this repository:

1. Read this file completely.
2. Read `docs/ORCA_PROJECT_CONTEXT.md` completely.
3. Inspect the current repository instead of assuming every item in the context file is already implemented.
4. Check `git status` and preserve unrelated user changes.

If code and documentation disagree, report the difference before making a large architectural change.

## 2. Project purpose

ORCA is a hackathon marine decision-support platform. It combines official marine data, deterministic Python calculations, caching, and later collaborative AI agents.

The MVP user journeys are:

- Find the nearest currently valid Potential Fishing Zone (PFZ).
- Summarize SST, chlorophyll, waves, currents, tides, wind, and weather.
- Identify active hazards and restricted areas.
- Produce an explainable sea-condition recommendation.
- Later compare candidate routes using deterministic risk rules.

ORCA is not an official navigation system. Never describe generated output as certified navigation advice.

## 3. Current architecture decision

The active hackathon MVP is **API-first and cache-assisted**.

```text
Client request
    -> FastAPI validation
    -> fresh-cache lookup
    -> official external source on cache miss
    -> Pydantic normalization
    -> cache normalized result
    -> deterministic Python calculation
    -> typed JSON / GeoJSON response
```

### Mandatory constraints

- The application must run without PostgreSQL, PostGIS, Supabase, SQLAlchemy, GeoAlchemy2, or Alembic.
- Do not add database schemas, migrations, repositories, ingestion tables, or persistence unless the user explicitly changes this decision.
- Database-related skeleton files may exist from an older experiment. They are not the active architecture and must not be imported by application startup or required by tests.
- Use an in-memory TTL cache by default.
- Redis may be supported as an optional cache, but Redis must not be required for local development or tests.
- Do not call every provider repeatedly when equivalent fresh data already exists in cache.
- “Real-time” means the latest official data available from the provider, respecting the provider's update frequency and validity window.

## 4. Engineering boundaries

### FastAPI routes

- Keep route handlers thin.
- Routes validate HTTP input, call a service, and return a typed response.
- Do not place HTML parsing, distance calculations, cache logic, or provider-specific request logic inside route modules.
- Put all public endpoints under `/v1`.
- Use Pydantic request and response models.
- Return stable machine-readable error codes in addition to human-readable messages.

### Services

- Services coordinate clients, parsers, caches, and deterministic calculations.
- Services must not depend directly on FastAPI request objects.
- Inject clients and caches so tests can replace them with fakes.
- Prefer small source-specific services over one large all-purpose module.

### External-source clients

- Use one shared asynchronous HTTPX infrastructure where practical.
- Every external request must define a timeout.
- Retry only transient failures such as connection errors, timeouts, and selected 5xx responses.
- Use bounded retries and short backoff. Never retry indefinitely.
- Limit concurrency with a semaphore when fetching many sectors or sources.
- A client fetches raw source data; it must not implement business recommendations.

### Parsers and normalization

- Keep parsing separate from networking.
- Convert raw provider responses into source-specific Pydantic models.
- Normalize timestamps to timezone-aware values.
- Preserve original source timestamps, retrieval time, validity, units, coordinates, and quality information.
- Reject malformed individual records while retaining valid records when safe to do so.
- Never silently invent a missing value.

### Deterministic logic

These operations must be implemented and tested in normal Python/geospatial code, never delegated to an LLM:

- Coordinate conversion.
- Haversine distance.
- Bearing and compass direction.
- Time-window and advisory-validity filtering.
- Unit conversion.
- Threshold checks.
- Geofence intersections.
- Route cost and safety veto rules.

For the hackathon-sized PFZ dataset, calculate nearest PFZ in Python. PostGIS is not required.

## 5. INCOIS PFZ rules

Treat all of the following as non-negotiable:

1. Never hard-code, persist, log, or manually configure `JSESSIONID`.
2. Create a fresh HTTP session for a new PFZ refresh attempt.
3. Bootstrap through:
   `https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en`
4. Discover current sector options from `TextDataHome`; do not assume only `SEC001` and `SEC002` exist.
5. Fetch sector pages with the same session used for bootstrap.
6. Validate sector pages using the expected live markers, including `#forecastdata` and `#satmsg`.
7. Parse the live region name, including the `#sectorname` selector variant.
8. Never hard-code a sector-to-region mapping. Store/return the sector code and parsed region name separately.
9. If page validation fails, retry once using a completely fresh session.
10. Convert DMS coordinates to decimal degrees using deterministic code.
11. Reject malformed PFZ rows individually while keeping valid rows and recording warnings.
12. Support known forecast-date forms such as `27 AUG 2026`, `27-Aug-2026`, `27/08/2026`, and `2026-08-27`.
13. Keep a raw-page date fallback because the live page structure can vary.
14. Preserve forecast date, validity text/time, source URL, retrieval time, and parsing warnings.
15. Ordinary automated tests must never call the live INCOIS site.
16. Add a saved HTML fixture and regression test whenever a new page variation is discovered.

## 6. Cache behavior

Use cache-aside behavior:

1. Build a stable source-specific cache key.
2. Return a fresh cached normalized result when present.
3. On a miss or expiry, fetch and normalize the official source.
4. Cache only successfully validated normalized data.
5. Keep the last successful value available as a stale fallback when practical.
6. If refresh fails and stale data exists, return it with `cache_status="stale"`, a warning, its retrieval time, and original validity.
7. If refresh fails and no usable cached data exists, return a typed `503 SOURCE_UNAVAILABLE` response.
8. Never label stale, expired, or incomplete evidence as current or safe.

Recommended cache-status values:

- `fresh` — served from an unexpired cache entry.
- `refreshed` — fetched from the provider during this request and cached.
- `stale` — last successful data returned because refresh failed.

Cache durations must be configurable per source. PFZ should primarily follow its advisory validity; weather and hazards should use shorter TTLs than SST/chlorophyll products.

## 7. Concurrent marine-source behavior

- Fetch independent sources concurrently with `asyncio.gather(..., return_exceptions=True)` or an equivalent controlled pattern.
- One failed source must not erase successful independent results.
- Return per-source status, retrieval time, freshness, and error information.
- A safety recommendation must become `INSUFFICIENT_EVIDENCE` when required evidence is unavailable or stale beyond an allowed limit.
- An active official warning must take precedence over a favorable model-derived score.

## 8. LLM and agent rules

LangGraph and LLM integration is a later layer, not the data or calculation layer.

An LLM may:

- Classify intent.
- Select tested tools.
- Coordinate specialist services.
- Explain already-computed results in the user's language.

An LLM must not:

- Fetch or scrape providers directly when a tested adapter exists.
- Calculate distance, bearing, validity, risk, or route geometry.
- Change source coordinates or timestamps.
- Fabricate missing marine data.
- Override official warnings or deterministic safety gates.

## 9. Testing requirements

- Use `pytest` and asynchronous test support where needed.
- No normal test may require internet access, PostgreSQL, Redis, or provider credentials.
- Use saved fixtures, fake clients, and mocked HTTP responses.
- Test success, malformed data, timeout, retry, partial failure, cache hit, cache miss, stale fallback, and no-fallback behavior.
- Test coordinate validation and boundary values.
- Test Haversine distance and bearing against known examples with explicit tolerances.
- Test that expired PFZ advisories are excluded.
- Test that an active official warning triggers the deterministic veto.
- Run the smallest relevant tests during development, then run the complete suite before handing off.

## 10. Configuration and security

- Keep secrets and provider credentials in environment variables.
- Maintain `.env.example` with names and safe placeholder values only.
- Never commit `.env`, tokens, cookies, credentials, downloaded private data, or session IDs.
- Do not log cookies, authorization headers, or full secret-bearing URLs.
- Keep optional integrations disabled by default when configuration is absent.

## 11. Change workflow for Codex

For every requested implementation:

1. Read the required context files.
2. Inspect the relevant current files and tests.
3. State a concise plan and list the files that will change.
4. Implement only the requested checkpoint.
5. Preserve working behavior and unrelated user changes.
6. Add or update tests with the implementation.
7. Run relevant tests and then the full suite when practical.
8. Report what changed, test results, remaining limitations, and the next safe checkpoint.

Do not create ZIP archives, duplicate repositories, database migrations, or broad rewrites unless the user explicitly asks.

## 12. Current implementation order

Build in this order:

1. Verify the restored second-ZIP baseline and tests.
2. Automatic INCOIS sector discovery.
3. Cached normalized PFZ advisory service.
4. Deterministic nearest-PFZ endpoint with JSON and GeoJSON.
5. First real marine-condition adapter.
6. Additional marine sources with partial-failure handling.
7. Deterministic safety assessment.
8. React/MapLibre integration.
9. LangGraph orchestration after deterministic services are stable.

