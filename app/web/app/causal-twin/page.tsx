import type { Metadata } from "next";
import { CausalTwinSurface } from "@/components/causal-twin/CausalTwinSurface";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";
import { RecordControl } from "@/components/session/RecordControl";
import { Unpublished } from "@/components/session/Unpublished";
import { UNCONNECTED } from "@/lib/causal-twin/source";

export const metadata: Metadata = { title: "Causal Twin" };

// The Realtime projection transport (#33) and sign-in (#87) exist, and the
// kernel can build the Twin's provenance (#75), but the Twin is not published
// as a projection this page reads yet, so the surface draws the honest
// unconnected state. Once it is, a live source replaces this constant and the
// same view draws the map.
const source = UNCONNECTED;

export default function CausalTwinPage() {
  return (
    <Page
      title="Causal Twin"
      question="Why does Serene believe what it believes?"
      lead="A map of what may influence what in your child’s days, drawn by how firmly each link is known. Choose any link to follow it down to the evidence."
      width={source.status === "ready" ? "wide" : "standard"}
      status={<RecordControl next="/causal-twin" />}
    >
      <Unpublished
        unconnected={<CausalTwinSurface source={source} />}
        signedIn={
          <EmptyState title="The map isn’t shown on the web yet">
            <p>
              Your family’s record is connected, but Serene does not yet send the Causal Twin to this
              page. Nothing is drawn rather than drawing a map that might not match the record.
            </p>
          </EmptyState>
        }
      />
    </Page>
  );
}
