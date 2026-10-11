import { describe, expect, it } from "vitest";
import { applyRow, ProjectionSync, type SyncState } from "./sync";
import { parseProjectionRow } from "./model";
import { CHILD, FakeFeed, OTHER_CHILD, flush, row } from "./testing";

function started(feed: FakeFeed) {
  const states: SyncState[] = [];
  const sync = new ProjectionSync(feed, CHILD, (s) => states.push(s));
  sync.start();
  const last = () => states[states.length - 1];
  const live = () => {
    const s = last();
    if (s.status !== "live") throw new Error(`expected live, got ${s.status}`);
    return s.projections;
  };
  return { sync, states, last, live };
}

const inv = (ids: string[]) => Object.fromEntries(ids.map((id) => [id, { status: "OPEN" }]));

describe("ProjectionSync: propagation", () => {
  it("is never live before the subscription is up and the snapshot is in", async () => {
    const feed = new FakeFeed();
    feed.write(row("active_investigations", 3, inv(["inv_1"])), { deliver: false });
    const { states } = started(feed);
    expect(states).toEqual([{ status: "connecting" }]);
    expect(feed.snapshotCalls).toBe(0);
  });

  it("propagates a projection change to the subscriber", async () => {
    const feed = new FakeFeed();
    feed.write(row("active_investigations", 3, inv([])), { deliver: false });
    const { live } = started(feed);
    feed.setStatus("subscribed");
    await flush();
    expect(live().active_investigations?.state).toEqual({});

    feed.write(row("active_investigations", 4, inv(["inv_1"])));
    expect(live().active_investigations?.state).toEqual(inv(["inv_1"]));
    expect(live().active_investigations?.last_sequence).toBe(4);
  });

  it("never moves backwards, ignores other children and repeats", async () => {
    const feed = new FakeFeed();
    const { live, states } = started(feed);
    feed.setStatus("subscribed");
    await flush();
    feed.write(row("pending_approvals", 9, { a: 1 }));
    const count = states.length;
    feed.emit(row("pending_approvals", 7, { a: 0 })); // late
    feed.emit(row("pending_approvals", 9, { a: 1 })); // repeat
    feed.emit(row("pending_approvals", 12, { a: 2 }, OTHER_CHILD)); // not ours
    expect(states.length).toBe(count);
    expect(live().pending_approvals?.state).toEqual({ a: 1 });
  });

  it("fails closed on a malformed change", async () => {
    const feed = new FakeFeed();
    const { last } = started(feed);
    feed.setStatus("subscribed");
    await flush();
    feed.emit({ ...row("active_learnings", 2), last_event_hash: "not-a-hash" });
    expect(last()).toEqual({ status: "error", reason: "a change from Serene did not pass its checks" });
  });
});

describe("ProjectionSync: reconnect and resync", () => {
  it("keeps but flags the last state while disconnected, then resyncs to the current state", async () => {
    const feed = new FakeFeed();
    feed.write(row("active_investigations", 3, inv([])), { deliver: false });
    const { last, live } = started(feed);
    feed.setStatus("subscribed");
    await flush();
    expect(live().active_investigations?.last_sequence).toBe(3);

    feed.setStatus("closed");
    expect(last()).toMatchObject({ status: "reconnecting" });
    // Changes made while disconnected are never delivered...
    feed.write(row("active_investigations", 5, inv(["inv_1"])), { deliver: false });
    feed.write(row("active_hypotheses", 5, { hyp_1: { level: "HYPOTHESIS" } }), { deliver: false });
    expect(last()).toMatchObject({ status: "reconnecting" });

    // ...but the resync on reconnect restores exactly what Postgres holds.
    feed.setStatus("subscribed");
    await flush();
    expect(feed.snapshotCalls).toBe(2);
    const expected = Object.fromEntries(feed.table.map((r) => [r.projection, parseProjectionRow(r)]));
    expect(live()).toEqual(expected);
  });

  it("folds changes that arrive during the snapshot the same way in any order", async () => {
    const results: unknown[] = [];
    const orders = [
      [4, 6, 5],
      [6, 5, 4],
      [5, 4, 6],
    ];
    for (const order of orders) {
      const feed = new FakeFeed();
      feed.write(row("current_child_state", 3, { n: 3 }), { deliver: false });
      feed.holdSnapshots = true;
      const { live } = started(feed);
      feed.setStatus("subscribed");
      for (const seq of order) feed.write(row("current_child_state", seq, { n: seq }));
      feed.release();
      await flush();
      results.push(live());
    }
    expect(results[0]).toMatchObject({ current_child_state: { last_sequence: 6, state: { n: 6 } } });
    expect(results[1]).toEqual(results[0]);
    expect(results[2]).toEqual(results[0]);
  });

  it("ignores a snapshot from an earlier connection", async () => {
    const feed = new FakeFeed();
    feed.write(row("active_learnings", 2, { old: true }), { deliver: false });
    feed.holdSnapshots = true;
    const { states } = started(feed);
    feed.setStatus("subscribed"); // first read held
    feed.setStatus("closed");
    feed.write(row("active_learnings", 8, { old: false }), { deliver: false });
    feed.holdSnapshots = false;
    feed.setStatus("subscribed"); // second read answers at once
    await flush();
    feed.release(); // the first, stale read finishes last
    await flush();
    const lastLive = [...states].reverse().find((s) => s.status === "live");
    expect(lastLive).toMatchObject({ projections: { active_learnings: { last_sequence: 8 } } });
    expect(states[states.length - 1]).toEqual(lastLive);
  });

  it("reports a failed snapshot and recovers on the next connection", async () => {
    const feed = new FakeFeed();
    feed.write(row("pending_approvals", 4), { deliver: false });
    feed.failSnapshots = true;
    const { last, live } = started(feed);
    feed.setStatus("subscribed");
    await flush();
    expect(last()).toEqual({ status: "error", reason: "Serene’s state could not be read" });
    feed.failSnapshots = false;
    feed.setStatus("closed");
    feed.setStatus("subscribed");
    await flush();
    expect(live().pending_approvals?.last_sequence).toBe(4);
  });

  it("stops listening when stopped", async () => {
    const feed = new FakeFeed();
    const { sync, states } = started(feed);
    sync.stop();
    expect(feed.subscribers).toBe(0);
    feed.setStatus("subscribed");
    await flush();
    expect(states).toEqual([{ status: "connecting" }]);
  });
});

describe("applyRow", () => {
  it("keeps the later row whatever order rows arrive in", () => {
    const a = parseProjectionRow(row("active_learnings", 2, { v: 2 }));
    const b = parseProjectionRow(row("active_learnings", 5, { v: 5 }));
    expect(applyRow(applyRow({}, a), b)).toEqual(applyRow(applyRow({}, b), a));
  });
});
