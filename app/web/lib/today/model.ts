import type { EpistemicLevel } from "@/lib/causal-twin/model";
import type { Experiment } from "@/lib/experiments/model";
import { experimentsSourceFrom } from "@/lib/experiments/source";
import type { Projections } from "@/lib/projections/sync";
import { wireReader } from "@/lib/wire";

// What Today reads beside the current investigation, from the same live
// projection rows (#33) for the chosen child. Each piece is validated against
// the kernel's own shape (serene/projections/views.py) and fails closed: a
// piece that does not pass is simply not drawn, never guessed at.

class TodayValidationError extends Error {}
const r = wireReader((path, problem) => {
  throw new TodayValidationError(`${path}: ${problem}`);
});

const LEVELS: Record<string, EpistemicLevel> = {
  RAW_EVIDENCE: 0,
  OBSERVATION: 1,
  PATTERN: 2,
  HYPOTHESIS: 3,
  TESTED_HYPOTHESIS: 4,
  CONTEXTUAL_LEARNING: 5,
};
const VERIFICATION = ["UNVERIFIED", "VERIFIED", "REJECTED", "NOT_APPLICABLE"] as const;
const LEARNING = ["ACTIVE", "NEEDS_REVIEW", "NEEDS_RETEST", "STALE", "DEPRECATED"] as const;

export type ChildState = {
  /** How many recorded items stand on each rung of the epistemic ladder. */
  byLevel: Record<EpistemicLevel, number>;
  evidence: Record<(typeof VERIFICATION)[number], number>;
};

export type Learning = {
  learning_id: string;
  status: (typeof LEARNING)[number];
  contexts: readonly string[];
  review_after: string;
};

function read<T>(fn: () => T): T | null {
  try {
    return fn();
  } catch (error) {
    if (error instanceof TodayValidationError) return null;
    throw error;
  }
}

/** `current_child_state`: counts by level and by evidence check, or null. */
export function childStateFrom(projections: Projections): ChildState | null {
  const row = projections.current_child_state;
  if (!row) return null;
  return read(() => {
    const v = r.object(row.state, "current_child_state");
    const levels = r.object(v.entities_by_level, "entities_by_level");
    const byLevel = { 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } as Record<EpistemicLevel, number>;
    for (const [name, count] of Object.entries(levels)) {
      const level = LEVELS[name];
      if (level === undefined) throw new TodayValidationError(`entities_by_level.${name}: unknown level`);
      byLevel[level] = r.integer(count, `entities_by_level.${name}`, 0, 1_000_000);
    }
    const ev = r.object(v.evidence_by_status, "evidence_by_status");
    const evidence = Object.fromEntries(
      VERIFICATION.map((s) => [s, r.integer(ev[s], `evidence_by_status.${s}`, 0, 1_000_000)]),
    ) as ChildState["evidence"];
    return { byLevel, evidence };
  });
}

/** `active_learnings`: what Serene has learned in context and still relies on, or null. */
export function learningsFrom(projections: Projections): Learning[] | null {
  const row = projections.active_learnings;
  if (!row) return null;
  return read(() =>
    Object.entries(r.object(row.state, "active_learnings")).map(([id, value]) => {
      const v = r.object(value, `active_learnings.${id}`);
      return {
        learning_id: r.id(id, `active_learnings.<key>`, "lrn"),
        status: r.oneOf(v.status, LEARNING, `active_learnings.${id}.status`),
        contexts: r.array(v.contexts, `active_learnings.${id}.contexts`, 16).map((t, i) => r.tag(t, `contexts[${i}]`)),
        review_after: r.timestamp(v.review_after, `active_learnings.${id}.review_after`),
      };
    }),
  );
}

/** Experiments waiting for the parent's decision, from the `experiments` projection. */
export function awaitingDecision(projections: Projections): Experiment[] | null {
  const row = projections.experiments;
  if (!row) return null;
  if (Object.keys(row.state).length === 0) return []; // nothing proposed
  const source = experimentsSourceFrom(row.state);
  if (source.status !== "ready") return null;
  return source.view.experiments.filter((e) => e.phase === "AWAITING_APPROVAL");
}
