import type { Metadata } from "next";
import { LiveExperiments } from "@/components/experiments/LiveExperiments";
import { Page } from "@/components/layout/Page";
import { RecordControl } from "@/components/session/RecordControl";
import { UNCONNECTED } from "@/lib/experiments/source";

export const metadata: Metadata = { title: "Experiments" };

// The kernel's `experiments` projection over the Realtime projection path
// (#33), for the signed-in parent's chosen child (#87), with decisions sent
// through the authenticated approval transport (#84). Signed out, unconfigured
// or with no child, the surface shows the honest unconnected state and offers
// nothing to decide.
export default function ExperimentsPage() {
  return (
    <Page
      title="Experiments"
      lead="Small, reversible changes you might try at home to tell one explanation from another."
      status={<RecordControl next="/experiments" />}
    >
      <LiveExperiments unconnected={UNCONNECTED} />
    </Page>
  );
}
