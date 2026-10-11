# Serene web shell

The Next.js application shell for Serene (Issue #34): a landing page with the
bloom, five primary surfaces (Today, Memory, Investigations, Experiments,
Causal Twin), responsive navigation, and shared layout primitives. It has no backend connection yet
and renders no family data; every surface shows an honest empty state until
projection state is streamed in (Issue #33).

```sh
npm ci
npm run dev         # http://localhost:3000
npm run typecheck
npm test            # unit and component tests (Vitest, jsdom)
npm run build
```

End-to-end checks run against a production build in Chromium at desktop
(1440px), tablet (768px) and phone (390px) sizes. They cover entering from the
landing page, exactly five surfaces, navigation and the current route, no
fabricated data, the skip link, the menu sheet (Esc and focus return), one h1
per route, no horizontal overflow from 360 to 1440px, a clean console,
reduced motion, and the brand assets. CI runs the same suite (`web-e2e`):

```sh
npx playwright install chromium   # once per machine
npm run test:e2e
```

The e2e build is made with `SERENE_FIXTURE_ROUTES=1`, which also routes the
test-only `page.fixture.tsx` pages (`/fixtures/causal-twin` draws the
synthetic Causal Twin). A normal `npm run build` has no such route and
bundles no fixture data. To look at the fixture map by hand:

```sh
SERENE_FIXTURE_ROUTES=1 npm run dev   # then open /fixtures/causal-twin
```

No API keys, model providers or external services are needed for any of
these commands.

## Layout

- `lib/surfaces.ts`: the five surfaces; the single source of navigation.
- `components/landing/`: `Landing`, the page at `/` and the only place the
  bloom grows. Entering clears the plate and flies the bloom's main flower
  into the logo's tile; the top bar, held empty on `/`, then fills in and
  Today opens.
- `components/shell/`: top bar with inline links (at least 60rem) and a menu
  sheet below that.
- `components/layout/`: `Page` (the plate every surface opens on),
  `EmptyState`, `SurfaceLoading`.
- `components/brand/`: `Hellebore` (one flower: five copies of the
  photographic petal, each pivoting at its base), the bloom (`BloomArt`: two
  hellebores, the bud, stems and frosted glass), the logo (`BloomMark`: the
  hellebore on a deep-olive tile) and `BloomDirector`, which plays the bloom
  on each fresh load of the landing page and ends it on any press, key or
  scroll.
- `components/notation/`: `LineMark` and `LineKey`, the certainty line
  notation (dotted = possibility, dashed = observed, solid = tested,
  struck = refuted, hollow = replaced).
- `lib/causal-twin/`: the Causal Twin as the kernel serializes it
  (`model.ts`, a mirror of `serene/causal/model.py` with a parser that
  re-checks the kernel's invariants and fails closed), how each edge is drawn
  (`categories.ts`), the React Flow graph and its deterministic layout
  (`graph.ts`), and where the twin comes from (`source.ts`: not connected
  until Issue #33).
- `components/causal-twin/`: `CausalTwinView` (unconnected, loading, error,
  empty and map states), the map (`TwinCanvas`, `VariableNode`,
  `BeliefEdge`), the selected-link summary (`SelectedLink`, where the
  provenance panel of Issue #39 attaches through `renderEdgeDetail`) and the
  text list of every link (`LinkList`).
- `fixtures/synthetic-causal-twin.json`: a synthetic twin for tests only. It
  is in the kernel's wire format and validates against
  `CausalTwin.model_validate_json`.
- `app/globals.css`: colour, type, space and motion tokens (light only),
  and the ruled grid. Palette: Warm Paper `#E0DFD8`, Sage Green `#A9B887`,
  Deep Olive `#2E3D28`. Motion respects `prefers-reduced-motion`. The full
  system is recorded in `DESIGN.md`, and the product context it serves in
  `PRODUCT.md`.

## Brand assets

The bloom is built from two photographic cutouts in `public/brand/bloom/`:
`petal.webp` and `bud.webp`, trimmed and converted from 1024px transparent PNG
masters (the prompts that generated them are in `PROMPTS.md`). Every flower,
the logo included, is the same petal.

The favicon and icons are exported from the running app, so they always match
the logo:

```sh
npm run build && npm run start      # in one shell
npm run brand:export                # in another
```

This writes `app/icon.png`, `app/apple-icon.png`, `app/favicon.ico` (16px and
32px), `public/brand/serene-mark.png` and `public/brand/serene-bloom.jpg`.
