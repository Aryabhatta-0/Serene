"use client";

import { useMemo } from "react";
import { InvestigationSurface } from "@/components/investigations/InvestigationSurface";
import type { FeedStatus, ProjectionFeed } from "@/lib/projections/sync";
import recorded from "@/fixtures/synthetic-investigation.json";

// The familiar investigation projection path, initialized at the end of the
// recorded fictional workflow so demo visitors can see the complete story.
type Handlers = { onRow: (row: unknown) => void; onStatus: (status: FeedStatus) => void };

export function DemoInvestigations({ mode }: { mode: "today" | "all" }) {
  const feed = useMemo<ProjectionFeed>(
    () => ({
      async fetchSnapshot() {
        const latest = new Map<string, unknown>();
        for (const row of [...recorded.snapshot, ...recorded.changes]) latest.set(row.projection, row);
        return [...latest.values()];
      },
      subscribe(_childId, handlers) {
        const h = handlers as Handlers;
        queueMicrotask(() => h.onStatus("subscribed"));
        return () => undefined;
      },
    }),
    [],
  );

  return <InvestigationSurface feed={feed} childId={recorded.snapshot[0].child_id} mode={mode} unconnected={null} />;
}
