import type { Metadata } from "next";
import { LiveCausalTwin } from "@/components/causal-twin/LiveCausalTwin";
import { Page } from "@/components/layout/Page";
import { RecordControl } from "@/components/session/RecordControl";

export const metadata: Metadata = { title: "Causal Twin" };

// The selected child's `causal_twin` projection on the signed-in family record
// (#33, #87): the twin and the complete provenance of every link (#75), with
// no child, actor or source ids. Only projection rows change what is drawn.
export default function CausalTwinPage() {
  return (
    <Page
      title="Causal Twin"
      question="Why does Serene believe what it believes?"
      lead="A map of what may influence what in your child’s days, drawn by how firmly each link is known. Choose any link to follow it down to the evidence."
      width="wide"
      status={<RecordControl next="/causal-twin" />}
    >
      <LiveCausalTwin />
    </Page>
  );
}
