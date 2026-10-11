import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import { MemoryView } from "@/components/memory/MemoryView";
import { memorySourceFrom } from "@/lib/memory/source";
import payload from "@/fixtures/synthetic-memory-dream.json";
import styles from "../causal-twin/fixture.module.css";

// TEST BUILDS ONLY. The `.fixture.tsx` extension is routed only when
// SERENE_FIXTURE_ROUTES=1 (next.config.mjs), which the Playwright suite sets;
// a normal build has no such page and never bundles the fixture. The view is
// synthetic: the kernel produced it from a made-up family
// (tests/memory_view_fixture.py), and it describes no real child.
export const metadata: Metadata = {
  title: "Memory (synthetic fixture)",
  robots: { index: false, follow: false },
};

export default function MemoryFixturePage() {
  // The same validation path a live projection will take.
  const source = memorySourceFrom(payload);
  return (
    <Page
      title="Memory"
      lead="Synthetic fixture: a made-up memory and Dream runs for testing how they are shown. It is not a family record."
    >
      <p role="note" className={styles.banner} data-fixture-banner>
        Synthetic test fixture. Nothing on this page describes a real child.
      </p>
      <MemoryView source={source} />
    </Page>
  );
}
