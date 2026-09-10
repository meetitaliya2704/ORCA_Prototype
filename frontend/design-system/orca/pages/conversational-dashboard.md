# ORCA conversational dashboard — F1 override

This page extends `../MASTER.md`; its reviewed ORCA safety overrides remain
authoritative.

- Desktop uses an approximately 64/36 conversation and answer/evidence layout
  so query context, suggestions, messages, and the composer remain usable.
- MapLibre is a lazy-loaded supporting visualization, closed until a spatial
  result offers an explicit View on map action.
- Mobile reads conversation, answer, evidence, warnings, optional map action,
  then advanced parameters; closing the map preserves page state.
- Journey inputs remain under the labelled Advanced query parameters disclosure.
- Status uses text and Lucide icons, never colour alone.
- Saved content says Demonstration; backend output says Deterministic ORCA result.
- Reduced motion, visible focus, 44 px controls, and long-token wrapping apply.

Forbidden wording remains: safe route, recommended route, navigation approval,
live agent, or any claim that PFZ data guarantees fish presence.

## Step 3A professional workspace override

- Desktop adds a compact collapsible deep-navy workspace sidebar while keeping
  one application route and one primary analysis workspace.
- Conversation remains the dominant surface. Query context sits directly above
  the message history; the answer/evidence column never invents numeric values
  absent from the assistant API contract.
- The live assistant is visually distinguished from demonstration fixtures and
  deterministic routing fallback. Conversation continuation uses the backend's
  opaque conversation ID without exposing database access to the browser.
- Query context opens initially, and the conversation card grows with its
  controls instead of clipping suggested questions behind the composer.
- Use system-first Inter fallbacks; no remote font, photograph, premium asset,
  chart, gradient hero, or animated marketing treatment is introduced.
- Marine character is limited to quiet grid, contour, and sonar geometry.
  Motion communicates processing and stops under reduced-motion preferences.
