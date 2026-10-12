# Serene web shell

The Next.js application shell for Serene (Issue #34): a landing page with the
bloom, five primary surfaces (Today, Memory, Investigations, Experiments,
Causal Twin), responsive navigation, read-only Twin/Memory review views, and
shared layout primitives. The #33 projection transport is implemented, but no
page subscribes: web sign-in (#84) and full Twin provenance projection (#75)
remain unfinished. Normal pages render no connected family data; fixture routes
are synthetic previews, not a deployed family connection.

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
synthetic Causal Twin, `/fixtures/memory` the synthetic memory and Dream
runs, `/fixtures/experiments` the synthetic experiments). A normal `npm run build` has no such route and bundles no fixture
data. To look at the fixture map by hand:

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
  (`graph.ts`), the provenance panel's reading of an edge (`provenance.ts`:
  ids typed by prefix, support against counterevidence, lineage and
  supersession followed by id), and where the twin comes from (`source.ts`:
  UNCONNECTED; wiring still requires sign-in and full Twin projection).
- `components/causal-twin/`: `CausalTwinSurface` (what pages render: the
  view with the provenance panel wired in), `CausalTwinView` (unconnected,
  loading, error, empty and map states), the map (`TwinCanvas`,
  `VariableNode`, `BeliefEdge`), the selected-link summary (`SelectedLink`),
  the provenance panel (`EdgeProvenance`, Issue #39, attached through
  `renderEdgeDetail`) and the text list of every link (`LinkList`). The
  panel shows only what `CausalEdge` carries; what it does not carry (what
  each item says, which evidence is external, which experiment an outcome
  came from) is stated in the panel, not filled in.
- `lib/projections/`: live projection state (Issue #33). The web app reads
  `serene.projection_state` only, never the event ledger
  (`no-ledger.test.ts` checks every source file). `sync.ts` takes a snapshot,
  then Realtime changes, and re-reads the snapshot on every (re)connect. Each
  projection keeps its highest ledger sequence, so the result does not depend
  on arrival order. It is never shown as live before the subscription is up.
  `supabase.ts` is the Supabase transport (PostgREST snapshot plus
  `postgres_changes`, both under the signed-in user's RLS), `client.ts` builds
  it from `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`
  (`config.ts`), and `useProjections` is the hook surfaces use.
  `components/projections/ProjectionStatus` says in words how current the
  state is. Web sign-in is not built yet (#84), so no page subscribes and
  surfaces stay unconnected.
- `lib/memory/`: consolidated memory and Dream runs as the kernel serializes
  them (`model.ts`, a mirror of `serene/memory/view.py` with a parser that
  re-checks its invariants and fails closed: a refused change can never be
  shown without its reasons), how reason codes, steps and outcomes are
  worded (`present.ts`), and where the view comes from (`source.ts`: not
  connected to a signed-in family source). `lib/wire.ts` holds the shared boundary readers.
- `components/memory/`: `MemoryView` (Issue #36: unconnected, loading, error,
  empty and review states), each kept memory with its evidence trail down to
  raw evidence, each Dream run with its steps and its kept, refused and
  waiting changes (`PatchCard`). It is read-only: nothing on it can edit,
  commit or approve memory.
- `lib/experiments/`: experiments and their approvals as the kernel serializes
  them (`model.ts`, a mirror of `serene/experiments/view.py`; its parser
  rejects any RED experiment that arrives open for a decision), the decision
  command (`approval.ts`: the exact `WebApprovalCommand` the kernel's
  `serene/adapters/web` channel accepts; it refuses to build an approval for
  RED and reads the kernel's answer strictly), wording (`present.ts`) and the
  source (`source.ts`).
- `components/experiments/`: `ExperimentsView` (Issue #37) groups experiments
  by what needs the parent, with intervention, risk, reversibility, approval,
  stage, outcomes and promotion result for each. `DecisionPanel` asks for
  confirmation, sends the command through an injected transport and shows
  only the kernel's answer; the stage changes only when the projection does.
  The shipped page passes no transport, so it offers no decision.
- `fixtures/synthetic-experiments.json` and `approval-command.example.json`:
  kernel output (`uv run python -m tests.experiments_view_fixture`), pinned by
  `tests/test_experiments_view.py` and `tests/test_web_approvals.py`. Drawn
  only by the test-build route `/fixtures/experiments`, whose scripted
  transport (`?answer=`) never reaches Serene.
- `fixtures/synthetic-memory-dream.json`: produced by running the kernel on a
  synthetic family (`uv run python -m tests.memory_view_fixture`);
  `tests/test_memory_view.py` fails if it drifts from what the kernel
  produces. Drawn only by the test-build route `/fixtures/memory`.
- `fixtures/synthetic-causal-twin.json`: a synthetic twin for tests only. It
  is in the kernel's wire format and validates against
  `CausalTwin.model_validate_json`.
- [app/globals.css](app/globals.css): colour, type, space and motion tokens (light only),
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

This writes [app/icon.png](app/icon.png), [app/apple-icon.png](app/apple-icon.png), [app/favicon.ico](app/favicon.ico) (16px and
32px), `public/brand/serene-mark.png` and `public/brand/serene-bloom.jpg`.
