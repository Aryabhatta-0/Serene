import type { Metadata } from "next";
import { CausalTwinSurface } from "@/components/causal-twin/CausalTwinSurface";
import { Page } from "@/components/layout/Page";
import { UNCONNECTED } from "@/lib/causal-twin/source";

export const metadata: Metadata = { title: "Causal Twin" };

// The twin projection is not connected yet (Issue #33), so the surface draws
// the honest unconnected state. Once it is, the live source replaces this
// constant and the same view draws the map.
const source = UNCONNECTED;

export default function CausalTwinPage() {
  return (
    <Page
      title="Causal Twin"
      lead="A map of what may influence what in your child’s days, drawn by how firmly each link is known."
      width={source.status === "ready" ? "wide" : "reading"}
    >
      <CausalTwinSurface source={source} />
    </Page>
  );
}
