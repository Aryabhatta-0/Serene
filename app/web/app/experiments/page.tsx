import type { Metadata } from "next";
import { LiveExperiments } from "@/components/experiments/LiveExperiments";
import { Page } from "@/components/layout/Page";
import { UNCONNECTED } from "@/lib/experiments/source";

export const metadata: Metadata = { title: "Experiments" };

// Decisions go through the authenticated approval transport (#84) once a
// parent is signed in with a child chosen (#87). The experiments themselves
// are not streamed yet: no `experiments` projection exists, so the surface
// draws the honest unconnected state and so offers nothing to decide.
const source = UNCONNECTED;

export default function ExperimentsPage() {
  return (
    <Page
      title="Experiments"
      lead="Small, reversible changes you might try at home to tell one explanation from another."
    >
      <LiveExperiments source={source} />
    </Page>
  );
}
