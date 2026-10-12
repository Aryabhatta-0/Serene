"use client";

import { useMemo } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { ProjectionStatus } from "@/components/projections/ProjectionStatus";
import { useFamilyRecord } from "@/components/session/FamilyRecord";
import { experimentsSourceFrom, type ExperimentsSource } from "@/lib/experiments/source";
import { webApprovalTransport } from "@/lib/experiments/transport";
import { useProjections, type ProjectionsState } from "@/lib/projections/useProjections";
import { ExperimentsView } from "./ExperimentsView";

// The Experiments surface on the signed-in family record: the kernel's
// `experiments` projection over the Realtime projection path (#33, #87), and
// the real decision transport (#84) for that child only. A decision goes to
// the kernel; the stage shown changes only when the projection does.

type Shown = { kind: "source"; source: ExperimentsSource } | { kind: "none-proposed" };

function shown(state: ProjectionsState, unconnected: ExperimentsSource): Shown {
  switch (state.status) {
    case "unconnected":
      return { kind: "source", source: unconnected };
    case "connecting":
      return { kind: "source", source: { status: "loading" } };
    case "error":
      return { kind: "source", source: { status: "error", reason: state.reason } };
  }
  const row = state.projections.experiments;
  // No row: the read side has not been published for this child (see backfill).
  if (!row) return { kind: "source", source: { status: "error", reason: "no experiments projection" } };
  if (Object.keys(row.state).length === 0) return { kind: "none-proposed" };
  return { kind: "source", source: experimentsSourceFrom(row.state) };
}

export function LiveExperiments({ unconnected }: { unconnected: ExperimentsSource }) {
  const { live, accessToken } = useFamilyRecord();
  const childId = live?.childId ?? null;
  const state = useProjections(live?.feed ?? null, childId);
  const decide = useMemo(() => (childId ? webApprovalTransport(childId, accessToken) : null), [childId, accessToken]);
  const view = shown(state, unconnected);
  const status = state.status === "live" || state.status === "reconnecting" ? <ProjectionStatus state={state} /> : null;
  return (
    <div key={childId ?? "none"}>
      {status}
      {view.kind === "none-proposed" ? (
        <EmptyState title="No experiments proposed yet">
          <p>Serene has not proposed any experiments. Each one will appear here before anything starts.</p>
        </EmptyState>
      ) : (
        <ExperimentsView source={view.source} decide={decide} />
      )}
    </div>
  );
}
