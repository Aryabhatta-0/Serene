import type { Metadata } from "next";
import { CausalTwinSurface } from "@/components/causal-twin/CausalTwinSurface";
import { Page } from "@/components/layout/Page";
import { twinSourceFrom } from "@/lib/causal-twin/source";
import payload from "@/fixtures/synthetic-causal-twin.json";
import styles from "./fixture.module.css";

// TEST BUILDS ONLY. The `.fixture.tsx` extension is routed only when
// SERENE_FIXTURE_ROUTES=1 (next.config.mjs), which the Playwright suite sets;
// a normal build has no such page and never bundles the fixture. The twin is
// synthetic: it describes no child and no family.
export const metadata: Metadata = {
  title: "Causal Twin (synthetic fixture)",
  robots: { index: false, follow: false },
};

export default function CausalTwinFixturePage() {
  // The same validation path a live projection will take.
  const source = twinSourceFrom(payload);
  return (
    <Page
      title="Causal Twin"
      lead="Synthetic fixture: a made-up twin for testing how the map is drawn. It is not a family record."
      width="wide"
    >
      <p role="note" className={styles.banner} data-fixture-banner>
        Synthetic test fixture. Nothing on this page describes a real child.
      </p>
      <CausalTwinSurface source={source} />
    </Page>
  );
}
