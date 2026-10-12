"use client";

import { useMemo, useRef, useState } from "react";
import { LiveInvestigations } from "@/components/investigations/LiveInvestigations";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";
import { FamilyRecordProvider } from "@/components/session/FamilyRecord";
import { RecordControl } from "@/components/session/RecordControl";
import { SignInForm } from "@/components/session/SignInForm";
import { FakeBackend } from "@/lib/auth/testing";
import type { FeedStatus, ProjectionFeed } from "@/lib/projections/sync";
import recorded from "@/fixtures/synthetic-investigation.json";
import styles from "../causal-twin/fixture.module.css";

// TEST BUILDS ONLY (imported only by page.fixture.tsx). The signed-in path of
// Issue #87 end to end in the browser, with Supabase replaced by a stand-in:
// a synthetic account that is the parent of two synthetic children, and a
// projection table that the kernel's recorded rows reach one append at a time.
// The record control, sign-in form, provider and surface are the real ones.

export const ACCOUNT = { email: "parent@example.org", password: "fake-synthetic-only", userId: "00000000-0000-4000-8000-000000000001" };
const CHILD = recorded.snapshot[0].child_id;
const SIBLING = `chd_${"5".repeat(32)}`;
type Row = (typeof recorded.snapshot)[number];
type Handlers = { onRow: (row: unknown) => void; onStatus: (status: FeedStatus) => void };

function siblingRows(): Row[] {
  const inv = structuredClone(recorded.snapshot.find((r) => r.projection === "investigations")!);
  const [id] = Object.keys(inv.state);
  (inv.state as Record<string, { question: string }>)[id].question = "Synthetic: why is bedtime slow?";
  return [{ ...inv, child_id: SIBLING, last_sequence: 3, last_event_hash: "3".padStart(64, "0") }];
}

export function FixtureFamily() {
  const applied = useRef(0); // recorded changes that have reached the table
  const subscription = useRef<{ childId: string; handlers: Handlers } | null>(null);
  const connected = useRef(true);
  const [count, setCount] = useState(0);

  const backend = useMemo(() => {
    const feed: ProjectionFeed = {
      async fetchSnapshot(childId) {
        if (childId === SIBLING) return siblingRows();
        if (childId !== CHILD) return [];
        const latest = new Map<string, unknown>();
        for (const row of [...recorded.snapshot, ...recorded.changes.slice(0, applied.current)]) {
          latest.set(row.projection, row);
        }
        return [...latest.values()];
      },
      subscribe(childId, handlers) {
        subscription.current = { childId, handlers };
        if (connected.current) queueMicrotask(() => handlers.onStatus("subscribed"));
        return () => {
          if (subscription.current?.handlers === handlers) subscription.current = null;
        };
      },
    };
    return new FakeBackend(feed, [ACCOUNT], { [ACCOUNT.userId]: [CHILD, SIBLING] });
  }, []);

  const next = recorded.changes[count];
  const deliverable = (childId: string) => connected.current && subscription.current?.childId === childId;

  return (
    <FamilyRecordProvider backend={backend}>
      <Page
        title="Today"
        lead="Synthetic fixture: signing in and following one child's record live. It is not a family record."
        status={<RecordControl next="/fixtures/session" />}
      >
        <p role="note" className={styles.banner} data-fixture-banner>
          Synthetic test fixture. Account {ACCOUNT.email}, password {ACCOUNT.password}. Nothing on this page describes a
          real child.
        </p>
        <div role="group" aria-label="Test controls" className={styles.banner} data-test-controls>
          <button
            type="button"
            className="button"
            disabled={!next}
            onClick={() => {
              // The kernel appends; its projection publish writes this row; Realtime delivers it.
              applied.current = count + 1;
              setCount(count + 1);
              if (deliverable(next.child_id)) subscription.current?.handlers.onRow(next);
            }}
          >
            Kernel append
          </button>{" "}
          <button
            type="button"
            className="button"
            onClick={() => {
              connected.current = false;
              subscription.current?.handlers.onStatus("closed");
            }}
          >
            Drop network
          </button>{" "}
          <button
            type="button"
            className="button"
            onClick={() => {
              connected.current = true;
              subscription.current?.handlers.onStatus("subscribed");
            }}
          >
            Restore network
          </button>{" "}
          <button type="button" className="button" onClick={() => backend.expire()}>
            Expire session
          </button>
        </div>
        <SignInForm next="/today" onSignedIn={() => {}} />
        <LiveInvestigations
          mode="today"
          unconnected={
            <EmptyState title="Nothing to review today">
              <p>No family record is connected, so there is nothing to report.</p>
            </EmptyState>
          }
        />
      </Page>
    </FamilyRecordProvider>
  );
}
