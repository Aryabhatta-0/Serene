import type { Metadata } from "next";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";

export const metadata: Metadata = { title: "Experiments" };

export default function ExperimentsPage() {
  return (
    <Page
      title="Experiments"
      lead="Small, reversible changes you might try at home to tell one explanation from another."
    >
      <EmptyState title="No experiments proposed">
        <p>
          Nothing starts without your approval. Each proposal will state the
          change, how risky it is, how to undo it, and what the result would
          mean. Anything judged unsafe cannot be approved.
        </p>
      </EmptyState>
    </Page>
  );
}
