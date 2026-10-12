"use client";

import type { TwinSource } from "@/lib/causal-twin/source";
import { CausalTwinView } from "./CausalTwinView";
import { EdgeProvenance } from "./EdgeProvenance";

// The Causal Twin surface as pages use it: the map, with the provenance
// panel (#39) filled in for whichever link is selected. The panel is only
// rendered once a link is chosen. With the provenance projection (#75) the
// panel shows the complete chain behind the link.
export function CausalTwinSurface({ source }: { source: TwinSource }) {
  const twin = source.status === "ready" ? source.twin : null;
  const provenance = source.status === "ready" ? (source.provenance ?? null) : null;
  return (
    <CausalTwinView
      source={source}
      renderEdgeDetail={
        twin
          ? (edge, { selectEdge }) => (
              <EdgeProvenance edge={edge} twin={twin} provenance={provenance} onSelectEdge={selectEdge} />
            )
          : undefined
      }
    />
  );
}
