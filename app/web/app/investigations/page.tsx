import type { Metadata } from "next";
import { InvestigationSurface } from "@/components/investigations/InvestigationSurface";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";

export const metadata: Metadata = { title: "Investigations" };

// Read from the `investigations` projection over the Realtime projection path
// (#33). Web sign-in is not built yet (#84), so no feed is passed and the
// surface shows the honest unconnected state.
export default function InvestigationsPage() {
  return (
    <Page
      title="Investigations"
      lead="Questions Serene is looking into, the explanations it is weighing, and the evidence it still needs."
    >
      <InvestigationSurface
        feed={null}
        childId={null}
        mode="all"
        unconnected={
          <EmptyState title="No open investigations">
            <p>
              An investigation opens when a concern has more than one plausible
              explanation. Serene will list each one, what supports it, and what
              would change its mind.
            </p>
          </EmptyState>
        }
      />
    </Page>
  );
}
