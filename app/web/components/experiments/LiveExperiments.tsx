"use client";

import { useMemo } from "react";
import { ProjectionStatus } from "@/components/projections/ProjectionStatus";
import { useFamilyRecord } from "@/components/session/FamilyRecord";
import { experimentsSourceFrom, UNCONNECTED, type ExperimentsSource } from "@/lib/experiments/source";
import { webApprovalTransport } from "@/lib/experiments/transport";
import type { ProjectionFeed } from "@/lib/projections/sync";
import { useProjections } from "@/lib/projections/useProjections";
import { ExperimentsView } from "./ExperimentsView";

// The Experiments surface with the real decision transport (Issue #84): a
// parent can decide only while signed in with a child chosen (#87), and only
// for that child. The decision goes to the kernel; the stage shown changes
// only when the kernel's record does.
export function LiveExperiments() {
  const { live, accessToken } = useFamilyRecord();
  if (!live) return <ExperimentsView source={UNCONNECTED} />;
  // Remount on child changes, discarding both previous data and decisions.
  return <ConnectedExperiments key={live.childId} {...live} accessToken={accessToken} />;
}

function ConnectedExperiments({ feed, childId, accessToken }: {
  feed: ProjectionFeed;
  childId: string;
  accessToken: () => Promise<string | null>;
}) {
  const state = useProjections(feed, childId);
  const transport = useMemo(() => webApprovalTransport(childId, accessToken), [childId, accessToken]);
  let source: ExperimentsSource;
  if (state.status === "error") source = { status: "error", reason: state.reason };
  else if (state.status === "live" || state.status === "reconnecting") {
    const row = state.projections.experiments;
    source = row ? experimentsSourceFrom(row.state) : UNCONNECTED;
  } else source = { status: "loading" };
  return (
    <>
      <ProjectionStatus state={state} />
      <ExperimentsView source={source} decide={state.status === "live" ? transport : null} />
    </>
  );
}
