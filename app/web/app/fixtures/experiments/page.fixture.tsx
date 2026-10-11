import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import { experimentsSourceFrom } from "@/lib/experiments/source";
import payload from "@/fixtures/synthetic-experiments.json";
import styles from "../causal-twin/fixture.module.css";
import { FixtureExperiments } from "./FixtureExperiments";

// TEST BUILDS ONLY. The `.fixture.tsx` extension is routed only when
// SERENE_FIXTURE_ROUTES=1 (next.config.mjs), which the Playwright suite sets;
// a normal build has no such page and never bundles the fixture. The view is
// synthetic: the kernel produced it from a made-up family
// (tests/experiments_view_fixture.py), and it describes no real child.
export const metadata: Metadata = {
  title: "Experiments (synthetic fixture)",
  robots: { index: false, follow: false },
};

export default function ExperimentsFixturePage() {
  // The same validation path a live projection will take.
  const source = experimentsSourceFrom(payload);
  return (
    <Page
      title="Experiments"
      lead="Synthetic fixture: made-up experiments in every stage, for testing how they are shown. It is not a family record."
    >
      <p role="note" className={styles.banner} data-fixture-banner>
        Synthetic test fixture. Nothing on this page describes a real child, and no decision here
        reaches Serene.
      </p>
      <FixtureExperiments source={source} />
    </Page>
  );
}
