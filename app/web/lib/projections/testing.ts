import type { FeedStatus, ProjectionFeed } from "./sync";

// A stand-in for serene.projection_state plus its Realtime channel, for unit
// tests only (imported by *.test.ts files, never by the app). `table` is what
// Postgres holds; `emit` delivers a change the way Realtime would; `setStatus`
// opens and drops the subscription; snapshots can be held to test races.

export type Row = {
  child_id: string;
  projection: string;
  state: Record<string, unknown>;
  last_sequence: number;
  last_event_hash: string;
};

export const CHILD = `chd_${"a".repeat(32)}`;
export const OTHER_CHILD = `chd_${"b".repeat(32)}`;

export function row(projection: string, sequence: number, state: Record<string, unknown> = {}, child = CHILD): Row {
  return {
    child_id: child,
    projection,
    state,
    last_sequence: sequence,
    last_event_hash: sequence.toString(16).padStart(64, "0"),
  };
}

export class FakeFeed implements ProjectionFeed {
  table: Row[] = [];
  subscribers = 0;
  snapshotCalls = 0;
  private handlers: { onRow: (row: unknown) => void; onStatus: (s: FeedStatus) => void } | null = null;
  private held: { resolve: (rows: unknown[]) => void; reject: (e: Error) => void }[] = [];
  holdSnapshots = false;
  failSnapshots = false;

  async fetchSnapshot(childId: string): Promise<unknown[]> {
    this.snapshotCalls += 1;
    if (this.failSnapshots) throw new Error("snapshot unavailable");
    const rows = this.table.filter((r) => r.child_id === childId).map((r) => ({ ...r }));
    if (!this.holdSnapshots) return rows;
    return new Promise((resolve, reject) => this.held.push({ resolve: () => resolve(rows), reject }));
  }

  subscribe(_childId: string, handlers: { onRow: (row: unknown) => void; onStatus: (s: FeedStatus) => void }) {
    this.handlers = handlers;
    this.subscribers += 1;
    return () => {
      this.handlers = null;
      this.subscribers -= 1;
    };
  }

  /** Postgres writes a row (as the kernel's projection publisher does) and Realtime delivers it. */
  write(r: Row, { deliver = true } = {}): void {
    this.table = [...this.table.filter((x) => !(x.child_id === r.child_id && x.projection === r.projection)), r];
    if (deliver) this.emit(r);
  }

  emit(r: unknown): void {
    this.handlers?.onRow(r);
  }

  setStatus(status: FeedStatus): void {
    this.handlers?.onStatus(status);
  }

  /** Let held snapshot reads finish, oldest first unless told otherwise. */
  release(order: "oldest-first" | "newest-first" = "oldest-first"): void {
    const held = order === "oldest-first" ? this.held : [...this.held].reverse();
    this.held = [];
    for (const h of held) h.resolve([]);
  }
}

export const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
