# ORCA frontend

This directory contains ORCA's assistant-first Next.js workspace. It preserves
the deterministic E3 nearest-PFZ journey and now connects the conversation UI
to the backend's typed `POST /v1/assistant/query` endpoint. The browser calls
FastAPI only and never calls Gemini, Supabase, INCOIS, Copernicus, or ECMWF
directly.

## Requirements and setup

- Node.js 20.9 or newer (F0 was verified with Node.js 24.9.0)
- npm 11 or newer
- A running ORCA FastAPI backend
- A MapLibre-compatible style URL whose attribution is suitable for display

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Configure `NEXT_PUBLIC_ORCA_API_BASE_URL` for FastAPI and
`NEXT_PUBLIC_MAP_STYLE_URL` for the map. Public variables are shipped to the
browser: never put credentials, provider tokens, or signed secret URLs in
them. The backend's `CORS_ALLOWED_ORIGINS` must explicitly include the
frontend origin.

`NEXT_PUBLIC_ORCA_DEMO_MODE=true` enables an explicit user action that loads
the sanitized saved E3 fixture. It is labelled **Demonstration Snapshot**, its
original generated time remains visible, and it is never used silently after
a live failure.

`NEXT_PUBLIC_ORCA_ASSISTANT_MODE` accepts `disabled`, `demo`, or `live`.
Disabled mode keeps deterministic E3 tools available. Demo mode replays the
sanitized `public/demo/conversation.json` fixture, always labelled
**Demonstration Conversation** with its original data time. Live mode calls
FastAPI and validates every response with Zod. It preserves the returned
conversation ID for follow-up turns, supports English, Hindi and Gujarati
request preferences, and exposes deterministic fallback without presenting it
as a Gemini response. `NEXT_PUBLIC_ORCA_PRESENTATION_MODE=true` improves
projector readability without auto-loading a fixture or hiding limitations.

## Conversational architecture

Ask ORCA supports runtime-validated user, live assistant, assistant
demonstration, deterministic result, clarification, tool activity, warning,
error, and system-notice messages. `AssistantTransport` keeps disabled, demo,
and HTTP transports separate. The HTTP transport sends only validated query
context and recent messages to ORCA; provider and database credentials remain
backend-only.

Predefined actions open the existing Advanced query parameters or replay saved
explanations. Live E3 responses appear as **Deterministic ORCA result**, update
the MapLibre map, and link evidence chips to authoritative structured cards.
The deterministic activity trace shows only response-proven operations; the
specialist demonstration trace is explicitly demo data, not hidden reasoning.

Desktop uses a compact collapsible sidebar and a wider, roughly 64/36
conversation-first split between Ask ORCA and the authoritative
answer/evidence panel. Query context opens initially, suggested questions are
not clipped by the composer, and the conversation card can grow with its
controls. Tablet stacks the evidence panel below the conversation, while
mobile keeps the composer reachable and follows conversation → answer →
evidence → optional map. The map
is closed by default and its
MapLibre JavaScript is lazy-loaded only after a spatial result exposes **View
on map**. A lightweight coordinate, distance, bearing, and direction summary
remains readable without it. The accessible map dialog returns focus when
closed and does not discard conversation or evidence state.

On mobile the reading order is Ask ORCA, deterministic answer, evidence and
warnings, optional View on map, then Advanced query parameters. The map opens
full-screen rather than displacing the answer. Tablet retains the same
assistant-first hierarchy.

The assistant response contract intentionally contains compact source
summaries rather than complete source payloads. The live result panel displays
only the values supplied by that contract. Advanced deterministic E3 controls
remain available for full numeric SST, chlorophyll, waves, wind, currents and
sea-level evidence cards.

## Commands

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
npm run start
```

The map interface uses the MIT-licensed MapCN registry component as locally
owned source code on top of MapLibre GL JS. ORCA supplies its configured map
style rather than MapCN's demonstration basemap. MapCN provides the map shell,
controls, markers, and popups; the journey reference line remains a resilient
screen-space overlay because it is explicitly not a navigable route.

The map style can fail independently from the E3 evidence. A missing style URL
shows a map-unavailable state while keeping the decision-support result
readable. The dashed line is a straight reference line, not a navigable or
recommended route.

## Safety and accessibility

ORCA is an educational decision-support prototype, not certified navigation
advice. Official meteorological and maritime warnings are not fully
integrated and must be checked independently. Operational limits are supplied
by the user; the frontend invents no vessel threshold.

The F0/F1 interface provides labelled inputs, focusable validation summaries,
visible keyboard focus, screen-reader status regions, 44 px controls,
text-and-icon status indicators, reduced-motion handling, safe token wrapping,
and a mobile-first layout. Messages use a semantic live log, keyboard Enter
submission, explicit cancel/reset controls, and focusable evidence links.

## Design guidance notice

F0 and F1 used the installed UI UX Pro Max repository snapshot at project commit
`886b964` as a development tool. Its master and ORCA-specific review are stored
in `design-system/orca/MASTER.md`; the F1 page override is in
`design-system/orca/pages/conversational-dashboard.md`. The skill is not a runtime
dependency, no premium assets were copied, and notices in the installed skill
repository remain authoritative for that tool.
