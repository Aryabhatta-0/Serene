import type { Metadata } from "next";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";

export const metadata: Metadata = { title: "Memory" };

export default function MemoryPage() {
  return (
    <Page
      title="Memory"
      lead="What Serene remembers about your family, and where each memory came from."
    >
      <EmptyState title="No memories yet">
        <p>
          A memory is only kept after review. Each one will link back to the
          evidence it came from, and anything Serene decided not to keep will
          say why.
        </p>
      </EmptyState>
    </Page>
  );
}
