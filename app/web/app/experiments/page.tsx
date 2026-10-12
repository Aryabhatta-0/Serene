import type { Metadata } from "next";
import { LiveExperiments } from "@/components/experiments/LiveExperiments";
import { Page } from "@/components/layout/Page";
import { RecordControl } from "@/components/session/RecordControl";

export const metadata: Metadata = { title: "Experiments" };

// The selected child's projection and authenticated transport share the
// existing family session. Only projection updates change displayed stages.

export default function ExperimentsPage() {
  return (
    <Page
      title="Experiments"
      question="What could we safely try?"
      lead="Small, reversible changes you might try at home to tell one explanation from another."
      status={<RecordControl next="/experiments" />}
    >
      <LiveExperiments />
    </Page>
  );
}
