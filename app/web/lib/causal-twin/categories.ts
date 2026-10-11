import type { Certainty } from "@/components/notation/LineMark";
import type { CausalEdge, LearningStatus } from "./model";

// How a Causal Twin edge is drawn. The category is read off the kernel's own
// verdict (`RelationshipStatus`, derived from the ledger) and never upgraded
// by the web app:
//
//   SUPPORTED                       -> tested      (approved experiment, in scope)
//   CANDIDATE with observations     -> observed    (co-occurrence, not cause)
//   CANDIDATE with nothing for it   -> hypothesis
//   REFUTED                         -> refuted     (kept, struck through)
//   SUPERSEDED                      -> superseded  (kept, replaced by a rival)
//
// A CANDIDATE that has been tested but is contradicted or awaiting a retest
// stays "observed" or "hypothesis": the kernel has not established it, so
// neither does the map. Its counterevidence is flagged separately.
export type EdgeCategory = "tested" | "observed" | "hypothesis" | "refuted" | "superseded";

export function categorize(edge: CausalEdge): EdgeCategory {
  switch (edge.status) {
    case "SUPPORTED":
      return "tested";
    case "REFUTED":
      return "refuted";
    case "SUPERSEDED":
      return "superseded";
    case "CANDIDATE":
      return edge.support.some((s) => s.kind === "OBSERVATIONAL") ? "observed" : "hypothesis";
  }
}

type CategoryMeta = {
  certainty: Certainty;
  /** What the link is, in a parent's words. */
  term: string;
  description: string;
};

// Ordered from most to least firmly held; the legend and the list follow it.
export const CATEGORY_ORDER: readonly EdgeCategory[] = [
  "tested",
  "observed",
  "hypothesis",
  "refuted",
  "superseded",
];

export const CATEGORIES: Record<EdgeCategory, CategoryMeta> = {
  tested: {
    certainty: "tested",
    term: "Tested in context",
    description:
      "Supported by an experiment you approved, and only within the situations it was tested in.",
  },
  observed: {
    certainty: "observed",
    term: "Observed",
    description: "Seen together in what has been recorded, but not tested. Not yet a cause.",
  },
  hypothesis: {
    certainty: "unknown",
    term: "Hypothesis",
    description: "A link Serene thinks is possible. Nothing recorded supports it yet.",
  },
  refuted: {
    certainty: "refuted",
    term: "Refuted",
    description: "Tested and contradicted. Kept on the map so the correction stays visible.",
  },
  superseded: {
    certainty: "superseded",
    term: "Replaced",
    description: "Set aside for a better-formed version of the idea. Kept so the change stays visible.",
  },
};

/** Recorded evidence against a link that the kernel has not (yet) refuted. */
export function isContested(edge: CausalEdge): boolean {
  return edge.status !== "REFUTED" && edge.counterevidence.length > 0;
}

// Learning validity (docs/epistemic-model.md section 5) a parent should see
// before relying on a tested link. ACTIVE needs no note.
export const LEARNING_NOTES: Partial<Record<LearningStatus, string>> = {
  NEEDS_REVIEW: "Due for review with you.",
  NEEDS_RETEST: "Needs a retest: something has changed since it was tested.",
  STALE: "Out of date: not reviewed in time, so it is no longer relied on.",
  DEPRECATED: "Retired: no longer relied on.",
};

/** A variable tag (`screen_time_before_bed`) as a parent reads it. */
export function variableLabel(tag: string): string {
  const words = tag.replace(/_+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
