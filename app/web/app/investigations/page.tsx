import type { Metadata } from "next";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";

export const metadata: Metadata = { title: "Investigations" };

export default function InvestigationsPage() {
  return (
    <Page
      title="Investigations"
      lead="Questions Serene is looking into, the explanations it is weighing, and the evidence it still needs."
    >
      <EmptyState title="No open investigations">
        <p>
          An investigation opens when a concern has more than one plausible
          explanation. Serene will list each one, what supports it, and what
          would change its mind.
        </p>
      </EmptyState>
    </Page>
  );
}
