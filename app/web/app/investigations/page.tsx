import type { Metadata } from "next";
import { LiveInvestigations } from "@/components/investigations/LiveInvestigations";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";
import { RecordControl } from "@/components/session/RecordControl";
import { DemoInvestigations } from "@/components/demo/DemoInvestigations";
import { DemoNotice } from "@/components/demo/DemoNotice";

export const metadata: Metadata = { title: "Investigations" };
export const dynamic = "force-dynamic";

// Read from the `investigations` projection over the Realtime projection path
// (#33), for the signed-in parent's chosen child (#87). Signed out,
// unconfigured or with no child, the surface shows the honest unconnected state.
export default function InvestigationsPage() {
  const demo = process.env.SERENE_DEMO_MODE === "1";
  return (
    <Page
      title="Investigations"
      question="What might be happening, and what evidence is needed?"
      lead="Questions Serene is looking into, the explanations it is weighing, and the evidence it still needs."
      status={<RecordControl next="/investigations" />}
    >
      {demo ? <DemoNotice /> : null}
      {demo ? (
        <DemoInvestigations mode="all" />
      ) : (
        <LiveInvestigations
          mode="all"
          unconnected={
            <EmptyState title="No open investigations">
              <p>
                An investigation opens when a concern has more than one plausible
                explanation. Serene sets the explanations side by side, asks for the
                evidence that would tell them apart, and checks that evidence before
                believing it.
              </p>
            </EmptyState>
          }
        />
      )}
    </Page>
  );
}
