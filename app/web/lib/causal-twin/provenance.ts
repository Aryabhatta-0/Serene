import type {
  ActorKind,
  CausalEdge,
  CausalTwin,
  DerivationMethod,
  EpistemicLevel,
  LearningStatus,
  VerificationStatus,
} from "./model";

// The provenance panel's reading of one edge (Issue #39). Everything here is
// derived from fields the kernel puts on `CausalEdge` (serene/causal/model.py)
// and from typed id prefixes (serene.domain.base.ID_PREFIXES); there is no
// second provenance model. Links between items follow ids, never display text.
//
// The twin carries ids, not the entities behind them, so the panel can say
// what kind of thing each item is and how it relates to the link, but not
// what it says. That is stated in the panel (see NOT_IN_TWIN), not filled in.

/** What an id refers to, read from its prefix. */
export type EntityKind =
  | "evidence"
  | "observation"
  | "pattern"
  | "hypothesis"
  | "experiment"
  | "outcome"
  | "learning"
  | "other";

const KIND_BY_PREFIX: Record<string, EntityKind> = {
  evd: "evidence",
  obs: "observation",
  pat: "pattern",
  hyp: "hypothesis",
  exp: "experiment",
  out: "outcome",
  lrn: "learning",
};

export function entityKind(id: string): EntityKind {
  return KIND_BY_PREFIX[id.slice(0, 3)] ?? "other";
}

export const KIND_LABELS: Record<EntityKind, string> = {
  evidence: "Raw evidence",
  observation: "Observation",
  pattern: "Pattern",
  hypothesis: "Link",
  experiment: "Experiment",
  outcome: "Experiment outcome",
  learning: "Learning",
  other: "Recorded item",
};

/** How an item bears on the link. Each role is named in text, never by colour alone. */
export type EvidenceRole =
  | "observation"
  | "evidence"
  | "outcome-supports"
  | "outcome-contradicts"
  | "outcome-inconclusive"
  | "observation-against"
  | "evidence-against"
  | "recorded";

export const ROLE_LABELS: Record<EvidenceRole, string> = {
  observation: "Observation",
  evidence: "Recorded evidence",
  "outcome-supports": "Experiment outcome: supports it",
  "outcome-contradicts": "Experiment outcome: contradicts it",
  "outcome-inconclusive": "Experiment outcome: inconclusive",
  "observation-against": "Observation against it",
  "evidence-against": "Evidence against it",
  recorded: "Recorded item",
};

export type EvidenceItem = { id: string; role: EvidenceRole };

/**
 * `CausalEdge.support`, in kernel order. EXPERIMENTAL items are SUPPORTS
 * outcomes of approved, completed experiments; OBSERVATIONAL items are the
 * hypothesis's own evidence and its patterns' observations.
 */
export function supportFor(edge: CausalEdge): EvidenceItem[] {
  return edge.support.map(({ entity_id: id, kind }) => {
    if (kind === "EXPERIMENTAL") return { id, role: "outcome-supports" };
    const entity = entityKind(id);
    return { id, role: entity === "observation" ? "observation" : entity === "evidence" ? "evidence" : "recorded" };
  });
}

/**
 * `CausalEdge.counterevidence`, contradicting outcomes first. The kernel
 * (policies/promotion.py `Counterevidence.all_ids`) puts only CONTRADICTS
 * and INCONCLUSIVE outcomes in it, so an outcome that is not listed in
 * `contradicting_outcomes` is an inconclusive one.
 */
export function againstFor(edge: CausalEdge): EvidenceItem[] {
  const contradicting = new Set(edge.contradicting_outcomes);
  const role = (id: string): EvidenceRole => {
    if (contradicting.has(id)) return "outcome-contradicts";
    switch (entityKind(id)) {
      case "outcome":
        return "outcome-inconclusive";
      case "observation":
        return "observation-against";
      case "evidence":
        return "evidence-against";
      default:
        return "recorded";
    }
  };
  const items = edge.counterevidence.map((id) => ({ id, role: role(id) }));
  return [
    ...items.filter((i) => i.role === "outcome-contradicts"),
    ...items.filter((i) => i.role !== "outcome-contradicts"),
  ];
}

/** An id that may name another link in the same twin. */
export type LinkRef = { id: string; edge: CausalEdge | null };

function linkRef(twin: CausalTwin, id: string): LinkRef {
  return { id, edge: twin.edges.find((e) => e.edge_id === id) ?? null };
}

export type Lineage = {
  /** `provenance.derived_from`: the link's direct parents. */
  parents: LinkRef[];
  /** `raw_evidence`: where the full chain ends, each marked if the link also declares it as a source. */
  raw: { id: string; declared: boolean }[];
  /** `provenance.source_ids` the twin's chain does not reach. Normally empty. */
  unreached: string[];
};

export function lineageOf(edge: CausalEdge, twin: CausalTwin): Lineage {
  const declared = new Set(edge.provenance.source_ids);
  const reached = new Set(edge.raw_evidence);
  return {
    parents: edge.provenance.derived_from.map((id) => linkRef(twin, id)),
    raw: edge.raw_evidence.map((id) => ({ id, declared: declared.has(id) })),
    unreached: edge.provenance.source_ids.filter((id) => !reached.has(id)),
  };
}

export type Supersession = {
  /** `provenance.supersedes` on this link. */
  replaces: LinkRef | null;
  /** Links in the twin whose `provenance.supersedes` is this link. */
  replacedBy: CausalEdge[];
};

export function supersessionOf(edge: CausalEdge, twin: CausalTwin): Supersession {
  const replaces = edge.provenance.supersedes;
  return {
    replaces: replaces === null ? null : linkRef(twin, replaces),
    replacedBy: twin.edges.filter((e) => e.provenance.supersedes === edge.edge_id),
  };
}

export function competingLinks(edge: CausalEdge, twin: CausalTwin): LinkRef[] {
  return edge.competing_edges.map((id) => linkRef(twin, id));
}

/**
 * Why the kernel holds the link in its current state, restating the rules in
 * serene/causal/model.py `_status`. It explains the verdict; it never adds one.
 */
export function verdictReason(edge: CausalEdge): string {
  const experimental = edge.support.some((s) => s.kind === "EXPERIMENTAL");
  switch (edge.status) {
    case "SUPPORTED":
      return "An experiment you approved supported it, and no experiment outcome contradicts it. It holds only in the situations listed under “Where and when it holds”.";
    case "REFUTED":
      return "An experiment outcome contradicted it, so Serene no longer relies on it. It stays on the map, with its evidence, so the correction can be checked.";
    case "SUPERSEDED":
      return "It was set aside for a better-formed version of the idea. Its evidence is kept here so the change can be checked.";
    case "CANDIDATE":
      if (edge.contradicting_outcomes.length > 0) {
        return "An experiment outcome contradicts it, so it is not treated as established.";
      }
      if (experimental && edge.learning_status !== null && !["ACTIVE", "NEEDS_REVIEW"].includes(edge.learning_status)) {
        return "An experiment supported it, but what was learned needs a retest or is out of date, so it is not relied on.";
      }
      if (experimental) {
        return "An experiment outcome supports it, but it has not yet passed Serene’s checks to count as tested.";
      }
      if (edge.support.length > 0) {
        return "It has been seen in what was recorded, but it has not been tested. Things happening together does not make one the cause.";
      }
      return "It was proposed as possible. Nothing recorded supports it yet.";
  }
}

export const LEVEL_NAMES: Record<EpistemicLevel, string> = {
  0: "Raw evidence",
  1: "Observation",
  2: "Pattern",
  3: "Hypothesis",
  4: "Tested hypothesis",
  5: "Contextual learning",
};

export const LEARNING_STATUS_LABELS: Record<LearningStatus, string> = {
  ACTIVE: "In use",
  NEEDS_REVIEW: "Due for review with you",
  NEEDS_RETEST: "Needs a retest",
  STALE: "Out of date",
  DEPRECATED: "Retired",
};

export const ACTOR_LABELS: Record<ActorKind, string> = {
  PARENT: "A parent",
  CAREGIVER: "A caregiver",
  AGENT: "Serene’s assistant (a language model)",
  POLICY: "One of Serene’s fixed rules",
  VERIFIER: "Serene’s evidence checker",
  SYSTEM: "Serene’s record keeping",
  MEMORY_COMMITTER: "Serene’s memory writer",
};

export const METHOD_LABELS: Record<DerivationMethod, string> = {
  PARENT_REPORT: "From a parent’s report",
  CAREGIVER_REPORT: "From a caregiver’s report",
  BROWSER_ACQUISITION: "Captured from a web source",
  MODEL_EXTRACTION: "Extracted by a language model",
  MODEL_INFERENCE: "Inferred by a language model",
  DETERMINISTIC_RULE: "By a fixed rule",
  EXPERIMENT_OUTCOME: "From an experiment outcome",
  HUMAN_REVIEW: "By a person’s review",
};

export const VERIFICATION_LABELS: Record<VerificationStatus, string> = {
  UNVERIFIED: "Not verified",
  VERIFIED: "Verified",
  REJECTED: "Rejected",
  NOT_APPLICABLE: "Not applicable",
};

/** What the twin does not carry, so the panel cannot show it. */
export const NOT_IN_TWIN: readonly string[] = [
  "What each observation or piece of evidence says, and when it was recorded.",
  "Whether a piece of evidence came from outside your family, such as a document or a web page.",
  "Which experiment each outcome came from, and whether each experiment has finished.",
  "The steps between the link’s direct sources and the raw evidence they rest on.",
  "The reason given when a link was replaced.",
];

const DATE = new Intl.DateTimeFormat("en-GB", { dateStyle: "long", timeZone: "UTC" });

/** A kernel timestamp as a calendar date (UTC, so server and browser agree). */
export function formatDate(iso: string): string {
  return DATE.format(new Date(iso));
}
