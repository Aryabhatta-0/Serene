import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import { MemoryView } from "@/components/memory/MemoryView";
import { UNCONNECTED } from "@/lib/memory/source";

export const metadata: Metadata = { title: "Memory" };

// The memory view is not connected yet (Issue #33), so the surface draws the
// honest unconnected state. Once it is, the live source replaces this
// constant and the same view shows memory and Dream runs.
const source = UNCONNECTED;

export default function MemoryPage() {
  return (
    <Page
      title="Memory"
      lead="What Serene remembers about your family, and where each memory came from."
    >
      <MemoryView source={source} />
    </Page>
  );
}
