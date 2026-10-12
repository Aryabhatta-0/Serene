import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import styles from "../causal-twin/fixture.module.css";
import { RecordedInvestigations } from "../investigations/RecordedInvestigations";

// TEST BUILDS ONLY. Routed only when SERENE_FIXTURE_ROUTES=1 (next.config.mjs);
// a normal build has no such page and never bundles the fixture. The data is
// kernel output for a synthetic family and describes no real child.
export const metadata: Metadata = {
  title: "Today (synthetic fixture)",
  robots: { index: false, follow: false },
};

export default function TodayFixturePage() {
  return (
    <Page
      title="Today"
      lead="Synthetic fixture: what Serene is working on in a made-up investigation recorded by the kernel. It is not a family record."
    >
      <p role="note" className={styles.banner} data-fixture-banner>
        Synthetic test fixture. Nothing on this page describes a real child.
      </p>
      <RecordedInvestigations mode="today" />
    </Page>
  );
}
