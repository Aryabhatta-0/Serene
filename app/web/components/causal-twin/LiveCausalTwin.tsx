"use client";

import { useMemo } from "react";
import { ProjectionStatus } from "@/components/projections/ProjectionStatus";
import { useFamilyRecord } from "@/components/session/FamilyRecord";
import { twinSourceFromProjection, UNCONNECTED, type TwinSource } from "@/lib/causal-twin/source";
import type { ProjectionFeed } from "@/lib/projections/sync";
import { useProjections, type ProjectionsState } from "@/lib/projections/useProjections";
import { CausalTwinSurface } from "./CausalTwinSurface";

// The Causal Twin on the signed-in family record: the selected child's
// `causal_twin` projection row (#33, #87), read through RLS like every other
// surface and never from the ledger. Nothing is drawn unless a parent is
// signed in with a child chosen; a session ending or a sign-out drops back to
// the unconnected state, and the twin goes with it.
export function LiveCausalTwin() {
  const { live } = useFamilyRecord();
  if (!live) return <CausalTwinSurface source={UNCONNECTED} />;
  // Remount on a child change: the previous child's twin, selection and open
  // panel are discarded before the next child's first row arrives.
  return <ConnectedCausalTwin key={live.childId} feed={live.feed} childId={live.childId} />;
}

function sourceOf(state: ProjectionsState): TwinSource {
  switch (state.status) {
    case "unconnected":
      return UNCONNECTED;
    case "connecting":
      return { status: "loading" };
    case "error":
      return { status: "error", reason: state.reason };
    case "live":
    case "reconnecting": {
      const row = state.projections.causal_twin;
      return row
        ? twinSourceFromProjection(row.state, row.last_event_hash)
        : { status: "error", reason: "no causal_twin projection" };
    }
  }
}

function ConnectedCausalTwin({ feed, childId }: { feed: ProjectionFeed; childId: string }) {
  const state = useProjections(feed, childId);
  const row = state.status === "live" || state.status === "reconnecting" ? state.projections.causal_twin : undefined;
  // Parsed once per state the sync reports, not once per render.
  const source = useMemo(() => sourceOf(state), [state]);
  return (
    <div data-twin-sequence={row?.last_sequence}>
      <ProjectionStatus state={state} />
      <CausalTwinSurface source={source} />
    </div>
  );
}
