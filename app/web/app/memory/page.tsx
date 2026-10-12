import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import { MemoryView } from "@/components/memory/MemoryView";
import { UNCONNECTED } from "@/lib/memory/source";

export const metadata: Metadata = { title: "Memory" };

// The Realtime projection transport (#33) and sign-in (#87) exist, but the
// memory view reads the Git memory repo as well as the ledger, so it is not a
// published projection yet (#99). The surface draws the honest unconnected
// state; once it is published, a live source replaces this constant and the
// same view shows memory and Dream runs.
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
