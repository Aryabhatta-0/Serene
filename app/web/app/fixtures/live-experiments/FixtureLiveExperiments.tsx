"use client";

import { useMemo, useRef, useState } from "react";
import { LiveExperiments } from "@/components/experiments/LiveExperiments";
import { Page } from "@/components/layout/Page";
import { FamilyRecordProvider } from "@/components/session/FamilyRecord";
import { RecordControl } from "@/components/session/RecordControl";
import { SignInForm } from "@/components/session/SignInForm";
import { FakeBackend } from "@/lib/auth/testing";
import { UNCONNECTED } from "@/lib/experiments/source";
import type { FeedStatus, ProjectionFeed } from "@/lib/projections/sync";
import payload from "@/fixtures/synthetic-experiments.json";
import styles from "../causal-twin/fixture.module.css";

// TEST BUILDS ONLY (imported only by page.fixture.tsx). The signed-in
// Experiments surface with the real LiveExperiments and the real approval
// transport (#84): decisions are POSTed to /api/approvals, which the browser
// test answers in place of the kernel. "Kernel publishes" then delivers the
// projection row the kernel writes once it has recorded the approval. The
// account, child and experiments are synthetic.

const ACCOUNT = {
  email: "parent@example.org",
  password: "fake-synthetic-only",
  userId: "00000000-0000-4000-8000-000000000001",
};
const CHILD = `chd_${"a".repeat(32)}`;
const GREEN = payload.experiments.find((e) => e.phase === "AWAITING_APPROVAL" && e.safety_class === "GREEN")!;
type Handlers = { onRow: (row: unknown) => void; onStatus: (status: FeedStatus) => void };

function experimentsRow(state: unknown, sequence: number) {
  return {
    child_id: CHILD,
    projection: "experiments",
    state,
    last_sequence: sequence,
    last_event_hash: sequence.toString(16).padStart(64, "0"),
  };
}

function approved() {
  const next = structuredClone(payload);
  const e = next.experiments.find((x) => x.experiment_id === GREEN.experiment_id)!;
  e.phase = "APPROVED";
  Object.assign(e.approval!, {
    state: "GRANTED",
    decided_at: "2026-09-07T12:00:00Z",
    decided_via: "WEB_APP",
    decision_open: false,
  });
  return next;
}

export function FixtureLiveExperiments() {
  const current = useRef(experimentsRow(payload, 40));
  const handlers = useRef<Handlers | null>(null);
  const [published, setPublished] = useState(false);
  const backend = useMemo(() => {
    const feed: ProjectionFeed = {
      async fetchSnapshot() {
        return [current.current];
      },
      subscribe(_childId, h) {
        handlers.current = h;
        queueMicrotask(() => h.onStatus("subscribed"));
        return () => {
          handlers.current = null;
        };
      },
    };
    return new FakeBackend(feed, [ACCOUNT], { [ACCOUNT.userId]: [CHILD] });
  }, []);
  return (
    <FamilyRecordProvider backend={backend}>
      <Page
        title="Experiments"
        lead="Synthetic fixture: deciding on an experiment through the real approval transport. It is not a family record."
        status={<RecordControl next="/fixtures/live-experiments" />}
      >
        <p role="note" className={styles.banner} data-fixture-banner>
          Synthetic test fixture. Account {ACCOUNT.email}, password {ACCOUNT.password}. Nothing on this page describes a
          real child.
        </p>
        <div role="group" aria-label="Test controls" className={styles.banner} data-test-controls>
          <button
            type="button"
            className="button"
            disabled={published}
            onClick={() => {
              current.current = experimentsRow(approved(), 41);
              setPublished(true);
              handlers.current?.onRow(current.current);
            }}
          >
            Kernel publishes
          </button>
        </div>
        <SignInForm next="/experiments" onSignedIn={() => {}} />
        <LiveExperiments unconnected={UNCONNECTED} />
      </Page>
    </FamilyRecordProvider>
  );
}
