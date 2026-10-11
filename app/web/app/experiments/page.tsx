import type { Metadata } from "next";
import { ExperimentsView } from "@/components/experiments/ExperimentsView";
import { Page } from "@/components/layout/Page";
import { UNCONNECTED } from "@/lib/experiments/source";

export const metadata: Metadata = { title: "Experiments" };

// The experiments view is not connected yet (Issue #33), and no transport
// carries a parent's decision to the kernel yet, so the surface draws the
// honest unconnected state and offers no decision.
const source = UNCONNECTED;

export default function ExperimentsPage() {
  return (
    <Page
      title="Experiments"
      lead="Small, reversible changes you might try at home to tell one explanation from another."
    >
      <ExperimentsView source={source} decide={null} />
    </Page>
  );
}
