import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import styles from "../causal-twin/fixture.module.css";
import { FixtureTwinProvenance } from "./FixtureTwinProvenance";

// TEST BUILDS ONLY. The `.fixture.tsx` extension is routed only when
// SERENE_FIXTURE_ROUTES=1 (next.config.mjs), which the Playwright suite sets;
// a normal build has no such page and never bundles the fixture. The twin and
// its provenance projection are kernel output for a synthetic family
// (tests/twin_provenance_fixture.py): they describe no child and no family.
export const metadata: Metadata = {
  title: "Causal Twin provenance (synthetic fixture)",
  robots: { index: false, follow: false },
};

export default function CausalTwinProvenanceFixturePage() {
  return (
    <Page
      title="Causal Twin"
      lead="Synthetic fixture: a kernel-generated twin with its full provenance, for testing the provenance panel. It is not a family record."
      width="wide"
    >
      <p role="note" className={styles.banner} data-fixture-banner>
        Synthetic test fixture. Nothing on this page describes a real child.
      </p>
      <FixtureTwinProvenance />
    </Page>
  );
}
