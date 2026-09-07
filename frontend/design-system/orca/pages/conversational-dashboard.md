# ORCA conversational dashboard — F1 override

This page extends `../MASTER.md`; its reviewed ORCA safety overrides remain
authoritative.

- Desktop uses a 52/48 conversation and answer/evidence layout.
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
