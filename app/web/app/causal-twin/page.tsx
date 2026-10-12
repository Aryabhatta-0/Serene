import type { Metadata } from "next";
import { CausalTwinSurface } from "@/components/causal-twin/CausalTwinSurface";
import { LiveCausalTwin } from "@/components/causal-twin/LiveCausalTwin";
import { DemoNotice } from "@/components/demo/DemoNotice";
import { Page } from "@/components/layout/Page";
import { RecordControl } from "@/components/session/RecordControl";
import demoPayload from "@/fixtures/synthetic-causal-twin.json";
import { twinSourceFrom } from "@/lib/causal-twin/source";

export const metadata: Metadata = { title: "Causal Twin" };
export const dynamic = "force-dynamic";

// The live page reads the selected child's `causal_twin` projection on the
// signed-in family record. Demo mode uses the same surface with fictional data.
export default function CausalTwinPage() {
  const demo = process.env.SERENE_DEMO_MODE === "1";
  return (
    <Page
      title="Causal Twin"
      question="Why does Serene believe what it believes?"
      lead="A map of what may influence what in your child’s days, drawn by how firmly each link is known. Choose any link to follow it down to the evidence."
      width="wide"
      status={<RecordControl next="/causal-twin" />}
    >
      {demo ? <DemoNotice /> : null}
      {demo ? <CausalTwinSurface source={twinSourceFrom(demoPayload)} /> : <LiveCausalTwin />}
    </Page>
  );
}
