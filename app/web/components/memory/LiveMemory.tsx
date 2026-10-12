"use client";

import { EmptyState } from "@/components/layout/EmptyState";
import { ProjectionStatus } from "@/components/projections/ProjectionStatus";
import { useFamilyRecord } from "@/components/session/FamilyRecord";
import { memorySourceFrom, UNCONNECTED, type MemorySource } from "@/lib/memory/source";
import type { ProjectionFeed } from "@/lib/projections/sync";
import { useProjections } from "@/lib/projections/useProjections";
import { MemoryView } from "./MemoryView";

export function LiveMemory() {
  const { live } = useFamilyRecord();
  if (!live) return <MemoryView source={UNCONNECTED} />;
  return <ConnectedMemory key={live.childId} {...live} />;
}

function ConnectedMemory({ feed, childId }: { feed: ProjectionFeed; childId: string }) {
  const state = useProjections(feed, childId);
  let source: MemorySource = { status: "loading" };
  let empty = false;
  if (state.status === "error") source = { status: "error", reason: state.reason };
  else if (state.status === "live" || state.status === "reconnecting") {
    const row = state.projections.memory_dream;
    const review = state.projections.memory_review;
    empty = !row && !!review && Object.keys(review.state).length === 0;
    source = row ? memorySourceFrom(row.state) : { status: "error", reason: "no memory projection" };
  }
  return (
    <>
      <ProjectionStatus state={state} />
      {empty ? (
        <EmptyState title="Nothing remembered yet">
          <p>Reviewed memories and Dream runs will appear here when Serene publishes them.</p>
        </EmptyState>
      ) : <MemoryView source={source} />}
    </>
  );
}
