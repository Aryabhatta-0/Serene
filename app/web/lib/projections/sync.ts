import { parseProjectionRow, type ProjectionName, type ProjectionRow } from "./model";

// Keeps one child's projection state in step with serene.projection_state
// (Issue #33): a snapshot, then live changes from Realtime, and a fresh
// snapshot every time the subscription is (re)established.
//
// Deterministic by construction. Each projection keeps the row with the
// highest ledger sequence it has seen, so the result does not depend on the
// order snapshot and changes arrive in: changes received while a snapshot is
// loading are buffered and folded in the same way. A reconnect always
// re-reads the snapshot, so nothing missed while disconnected is lost.
// Nothing is ever shown as live unless the subscription says it is.

export type Projections = Partial<Record<ProjectionName, ProjectionRow>>;

export type SyncState =
  | { status: "connecting" }
  | { status: "live"; projections: Projections }
  /** Disconnected after being live: the last state is kept but is no longer current. */
  | { status: "reconnecting"; projections: Projections }
  | { status: "error"; reason: string };

export type FeedStatus = "subscribed" | "closed" | "error";

/** What the sync needs from a transport. `supabaseProjectionFeed` is the real one. */
export interface ProjectionFeed {
  /** Every projection_state row for the child, as stored. */
  fetchSnapshot(childId: string): Promise<unknown[]>;
  /** Live row changes. Returns an unsubscribe function. */
  subscribe(
    childId: string,
    handlers: { onRow: (row: unknown) => void; onStatus: (status: FeedStatus) => void },
  ): () => void;
}

/** Fold one row in: a projection only ever moves forward in the ledger. */
export function applyRow(projections: Projections, row: ProjectionRow): Projections {
  const current = projections[row.projection];
  if (current && current.last_sequence > row.last_sequence) return projections;
  if (current && current.last_sequence === row.last_sequence && current.last_event_hash === row.last_event_hash) {
    return projections;
  }
  return { ...projections, [row.projection]: row };
}

export class ProjectionSync {
  private projections: Projections | null = null;
  private buffer: ProjectionRow[] = [];
  private syncing = false;
  private generation = 0;
  private unsubscribe: (() => void) | null = null;
  private stopped = false;

  constructor(
    private readonly feed: ProjectionFeed,
    private readonly childId: string,
    private readonly onState: (state: SyncState) => void,
  ) {}

  start(): void {
    this.onState({ status: "connecting" });
    this.unsubscribe = this.feed.subscribe(this.childId, {
      onRow: (raw) => this.receive(raw),
      onStatus: (status) => this.status(status),
    });
  }

  stop(): void {
    this.stopped = true;
    this.generation += 1;
    this.unsubscribe?.();
    this.unsubscribe = null;
  }

  private status(status: FeedStatus): void {
    if (this.stopped) return;
    if (status === "subscribed") {
      void this.resync();
      return;
    }
    // Not live any more: keep what was shown, say plainly it may be out of date.
    this.syncing = false;
    this.generation += 1;
    this.onState(
      this.projections ? { status: "reconnecting", projections: this.projections } : { status: "connecting" },
    );
  }

  private receive(raw: unknown): void {
    if (this.stopped) return;
    let row: ProjectionRow;
    try {
      row = parseProjectionRow(raw);
    } catch {
      return this.fail("a change from Serene did not pass its checks");
    }
    if (row.child_id !== this.childId) return; // not this child's: never shown
    if (this.syncing || this.projections === null) {
      this.buffer.push(row);
      return;
    }
    const next = applyRow(this.projections, row);
    if (next !== this.projections) {
      this.projections = next;
      this.onState({ status: "live", projections: next });
    }
  }

  private async resync(): Promise<void> {
    const generation = ++this.generation;
    this.syncing = true;
    let rows: ProjectionRow[];
    try {
      const raw = await this.feed.fetchSnapshot(this.childId);
      rows = raw.map((row, i) => parseProjectionRow(row, `snapshot[${i}]`));
    } catch {
      if (generation === this.generation) this.fail("Serene’s state could not be read");
      return;
    }
    if (generation !== this.generation || this.stopped) return; // superseded by a newer (re)connect
    if (rows.some((row) => row.child_id !== this.childId)) return this.fail("the snapshot was for another child");
    // The snapshot replaces what was held; buffered changes fold in by sequence.
    let next: Projections = {};
    for (const row of [...rows, ...this.buffer]) {
      if (row.child_id === this.childId) next = applyRow(next, row);
    }
    this.buffer = [];
    this.syncing = false;
    this.projections = next;
    this.onState({ status: "live", projections: next });
  }

  private fail(reason: string): void {
    this.syncing = false;
    this.generation += 1;
    this.projections = null;
    this.buffer = [];
    this.onState({ status: "error", reason });
  }
}
