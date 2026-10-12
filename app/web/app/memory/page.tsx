import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import { LiveMemory } from "@/components/memory/LiveMemory";

export const metadata: Metadata = { title: "Memory" };

export default function MemoryPage() {
  return (
    <Page
      title="Memory"
      lead="What Serene remembers about your family, and where each memory came from."
    >
      <LiveMemory />
    </Page>
  );
}
