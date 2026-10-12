import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import { LiveMemory } from "@/components/memory/LiveMemory";
import { RecordControl } from "@/components/session/RecordControl";

export const metadata: Metadata = { title: "Memory" };

export default function MemoryPage() {
  return (
    <Page
      title="Memory"
      question="What has Serene learned and kept?"
      lead="What Serene remembers about your family, why each memory is kept, and where it came from."
      status={<RecordControl next="/memory" />}
    >
      <LiveMemory />
    </Page>
  );
}
