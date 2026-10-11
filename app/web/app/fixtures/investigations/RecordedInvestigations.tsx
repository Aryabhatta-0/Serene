"use client";

import { useMemo, useRef, useState } from "react";
import { InvestigationSurface } from "@/components/investigations/InvestigationSurface";
import type { FeedStatus, ProjectionFeed } from "@/lib/projections/sync";
import recorded from "@/fixtures/synthetic-investigation.json";
import styles from "../causal-twin/fixture.module.css";

// TEST BUILDS ONLY (imported only by page.fixture.tsx files). A feed that
// replays the projection_state rows the kernel recorded for a synthetic
// investigation (tests/investigation_view_fixture.py): the snapshot, then each
// later change, delivered one at a time as Realtime would. The surface reads
// them through the same ProjectionSync path it uses live (#33).
type Handlers = { onRow: (row: unknown) => void; onStatus: (status: FeedStatus) => void };

export function RecordedInvestigations({ mode }: { mode: "today" | "all" }) {
  const handlers = useRef<Handlers | null>(null);
  const applied = useRef(0); // changes that have reached the table
  const [count, setCount] = useState(0);
  const feed = useMemo<ProjectionFeed>(
    () => ({
      // The table as it stands: the snapshot plus every change applied so far.
      async fetchSnapshot() {
        const latest = new Map<string, unknown>();
        for (const row of [...recorded.snapshot, ...recorded.changes.slice(0, applied.current)]) {
          latest.set(row.projection, row);
        }
        return [...latest.values()];
      },
      subscribe(_childId, h) {
        handlers.current = h;
        queueMicrotask(() => h.onStatus("subscribed"));
        return () => {
          handlers.current = null;
        };
      },
    }),
    [],
  );
  const next = recorded.changes[count];
  return (
    <>
      <div role="group" aria-label="Test controls" className={styles.banner} data-test-controls>
        <button
          type="button"
          className="button"
          disabled={!next}
          onClick={() => {
            applied.current = count + 1;
            setCount(count + 1);
            handlers.current?.onRow(next);
          }}
        >
          Deliver next recorded change
        </button>{" "}
        <button
          type="button"
          className="button"
          onClick={() => {
            // Every later change reaches the table while disconnected, and none
            // is delivered: only the resync on reconnect can show them.
            handlers.current?.onStatus("closed");
            applied.current = recorded.changes.length;
            setCount(recorded.changes.length);
          }}
        >
          Drop connection
        </button>{" "}
        <button type="button" className="button" onClick={() => handlers.current?.onStatus("subscribed")}>
          Reconnect
        </button>
      </div>
      <InvestigationSurface feed={feed} childId={recorded.snapshot[0].child_id} mode={mode} unconnected={null} />
    </>
  );
}
