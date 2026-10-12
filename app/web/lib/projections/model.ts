import { wireReader } from "@/lib/wire";

// One row of serene.projection_state (supabase/migrations): disposable read
// state rebuilt by replaying the ledger, with the ledger position it reflects.
// This is the only Serene table the web app reads for record content (Issue
// #33); the only other is serene.child_guardians, to list a parent's children
// (#87, lib/auth/backend.ts). The immutable event ledger is never the UI's
// view model.

export const PROJECTION_NAMES = [
  "current_child_state",
  "active_investigations",
  "active_hypotheses",
  "pending_approvals",
  "active_learnings",
  "investigations", // issue #35
  "experiments", // issues #37, #84
  "causal_twin", // the Causal Twin surface (#75)
] as const;
export type ProjectionName = (typeof PROJECTION_NAMES)[number];

export type ProjectionRow = {
  child_id: string;
  projection: ProjectionName;
  state: Record<string, unknown>;
  last_sequence: number;
  last_event_hash: string;
};

export class ProjectionValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProjectionValidationError";
  }
}

function fail(path: string, problem: string): never {
  throw new ProjectionValidationError(`${path}: ${problem}`);
}
const r = wireReader(fail);

/** Validate one row from Postgres or Realtime, or throw ProjectionValidationError. */
export function parseProjectionRow(value: unknown, path = "row"): ProjectionRow {
  const row = r.object(value, path);
  return {
    child_id: r.id(row.child_id, `${path}.child_id`, "chd"),
    projection: r.oneOf(row.projection, PROJECTION_NAMES, `${path}.projection`),
    state: r.object(row.state, `${path}.state`),
    last_sequence: r.integer(row.last_sequence, `${path}.last_sequence`, 0, Number.MAX_SAFE_INTEGER),
    last_event_hash: r.sha256(row.last_event_hash, `${path}.last_event_hash`),
  };
}
