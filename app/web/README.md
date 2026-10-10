# Serene web shell

The Next.js application shell for Serene (Issue #34): five primary surfaces
(Today, Memory, Investigations, Experiments, Causal Twin), responsive
navigation, and shared layout primitives. It has no backend connection yet
and renders no family data; every surface shows an honest empty state until
projection state is streamed in (Issue #33).

```sh
npm ci
npm run dev         # http://localhost:3000
npm run typecheck
npm run build
```

End-to-end checks (navigation across all five surfaces, no fabricated data,
skip link) run against a production build in Chromium:

```sh
npx playwright install chromium   # once per machine
npm run test:e2e
```

No API keys, model providers or external services are needed for any of
these commands.

## Layout

- `lib/surfaces.ts`: the five surfaces; the single source of navigation.
- `components/shell/`: rail (desktop, at least 64rem), inline top bar
  (45 to 64rem) and menu sheet (phones).
- `components/layout/`: `Page`, `EmptyState`, `SurfaceLoading`.
- `components/notation/`: `LineMark` and `LineKey`, the certainty line
  notation (dotted = possibility, dashed = observed, solid = tested,
  struck = refuted).
- `app/globals.css`: colour, type, space and motion tokens, light and dark.
  Motion respects `prefers-reduced-motion`.
