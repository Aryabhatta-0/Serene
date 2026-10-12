"use client";

import { CausalTwinSurface } from "@/components/causal-twin/CausalTwinSurface";
import { twinSourceFrom } from "@/lib/causal-twin/source";
import payload from "@/fixtures/synthetic-twin-provenance.json";

// TEST BUILDS ONLY (see page.fixture.tsx). Parsed in the browser, through the
// same validation a live twin and its provenance projection will take.
export function FixtureTwinProvenance() {
  return <CausalTwinSurface source={twinSourceFrom(payload.twin, payload.provenance)} />;
}
