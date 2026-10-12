// The Causal Twin as the surface holds it. Two wire formats are read into it:
// the kernel's own `CausalTwin.model_dump(mode="json")` (serene/causal/model.py,
// Issue #27), which the canonical Maya report and the fixtures carry, and the
// live `causal_twin` projection (web-model.ts). Field names and enums mirror
// the Pydantic models.
//
// The view model holds no child or actor id. `parseCausalTwin` checks the ids
// the kernel format carries (every edge is the same child's) and drops them,
// so nothing the surface keeps or renders can show one.
//
// The web app never decides what an edge means. `parseCausalTwin` re-checks
// the kernel's own invariants at the boundary and rejects anything else, so a
// malformed or tampered payload fails closed instead of being drawn as belief.

export const TWIN_VERSION = "causal-twin/1";

export type RelationshipStatus = "CANDIDATE" | "SUPPORTED" | "REFUTED" | "SUPERSEDED";
export type SupportKind = "OBSERVATIONAL" | "EXPERIMENTAL";
export type LearningStatus = "ACTIVE" | "NEEDS_REVIEW" | "NEEDS_RETEST" | "STALE" | "DEPRECATED";

/** The six-rung ladder (serene.domain.values.EpistemicLevel). */
export const EpistemicLevel = {
  RAW_EVIDENCE: 0,
  OBSERVATION: 1,
  PATTERN: 2,
  HYPOTHESIS: 3,
  TESTED_HYPOTHESIS: 4,
  CONTEXTUAL_LEARNING: 5,
} as const;
export type EpistemicLevel = (typeof EpistemicLevel)[keyof typeof EpistemicLevel];

export type ActorKind =
  | "PARENT"
  | "CAREGIVER"
  | "AGENT"
  | "POLICY"
  | "VERIFIER"
  | "SYSTEM"
  | "MEMORY_COMMITTER";

export type DerivationMethod =
  | "PARENT_REPORT"
  | "CAREGIVER_REPORT"
  | "BROWSER_ACQUISITION"
  | "MODEL_EXTRACTION"
  | "MODEL_INFERENCE"
  | "DETERMINISTIC_RULE"
  | "EXPERIMENT_OUTCOME"
  | "HUMAN_REVIEW";

export type VerificationStatus = "UNVERIFIED" | "VERIFIED" | "REJECTED" | "NOT_APPLICABLE";

export type ModelRef = {
  provider: string;
  model_id: string;
  prompt_version: string;
  runtime: string;
};

export type Provenance = {
  created_by: { kind: ActorKind };
  created_at: string;
  method: DerivationMethod;
  model: ModelRef | null;
  derived_from: readonly string[];
  source_ids: readonly string[];
  verification_status: VerificationStatus;
  supersedes: string | null;
};

export type Scope = { contexts: readonly string[] };
export type ValidityWindow = { valid_from: string; review_after: string };
export type SupportItem = { entity_id: string; kind: SupportKind };

export type CausalEdge = {
  edge_id: string;
  relationship: string;
  cause: string | null;
  effect: string | null;
  status: RelationshipStatus;
  epistemic_level: EpistemicLevel;
  support: readonly SupportItem[];
  counterevidence: readonly string[];
  contradicting_outcomes: readonly string[];
  confounders: readonly string[];
  alternative_explanations: readonly string[];
  competing_edges: readonly string[];
  experiments: readonly string[];
  scope: Scope;
  validity: ValidityWindow | null;
  learning_status: LearningStatus | null;
  provenance: Provenance;
  raw_evidence: readonly string[];
};

export type CausalTwin = {
  ledger_head: string;
  edges: readonly CausalEdge[];
};

export class TwinValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TwinValidationError";
  }
}

const RELATIONSHIP_STATUSES: readonly RelationshipStatus[] = [
  "CANDIDATE",
  "SUPPORTED",
  "REFUTED",
  "SUPERSEDED",
];
const SUPPORT_KINDS: readonly SupportKind[] = ["OBSERVATIONAL", "EXPERIMENTAL"];
const LEARNING_STATUSES: readonly LearningStatus[] = [
  "ACTIVE",
  "NEEDS_REVIEW",
  "NEEDS_RETEST",
  "STALE",
  "DEPRECATED",
];
export const ACTOR_KINDS: readonly ActorKind[] = [
  "PARENT",
  "CAREGIVER",
  "AGENT",
  "POLICY",
  "VERIFIER",
  "SYSTEM",
  "MEMORY_COMMITTER",
];
export const DERIVATION_METHODS: readonly DerivationMethod[] = [
  "PARENT_REPORT",
  "CAREGIVER_REPORT",
  "BROWSER_ACQUISITION",
  "MODEL_EXTRACTION",
  "MODEL_INFERENCE",
  "DETERMINISTIC_RULE",
  "EXPERIMENT_OUTCOME",
  "HUMAN_REVIEW",
];
export const VERIFICATION_STATUSES: readonly VerificationStatus[] = [
  "UNVERIFIED",
  "VERIFIED",
  "REJECTED",
  "NOT_APPLICABLE",
];
// serene.domain.base.ID_PREFIXES
const ENTITY_PREFIXES = new Set([
  "chd", "act", "src", "evt", "evd", "obs", "pat", "hyp",
  "inv", "exp", "trl", "out", "lrn", "mpt", "apr", "erq",
]);
const TRUSTED_LEARNING: ReadonlySet<LearningStatus | null> = new Set(["ACTIVE", "NEEDS_REVIEW"]);

const ID_RE = /^([a-z]{3})_[0-9a-f]{32}$/;
const TAG_RE = /^[a-z][a-z0-9_]{0,63}$/;
const SHA256_RE = /^[0-9a-f]{64}$/;

export type Json = Record<string, unknown>;

function fail(path: string, problem: string): never {
  throw new TwinValidationError(`${path}: ${problem}`);
}

function object(value: unknown, path: string): Json {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail(path, "expected an object");
  return value as Json;
}

function array(value: unknown, path: string, max: number, min = 0): unknown[] {
  if (!Array.isArray(value)) fail(path, "expected a list");
  if (value.length < min || value.length > max) fail(path, `expected ${min} to ${max} items`);
  return value;
}

function text(value: unknown, path: string, max = 500): string {
  if (typeof value !== "string" || value.length < 1 || value.length > max) fail(path, "expected text");
  return value;
}

function id(value: unknown, path: string, prefix?: string): string {
  const match = typeof value === "string" ? ID_RE.exec(value) : null;
  if (!match || !ENTITY_PREFIXES.has(match[1]) || (prefix && match[1] !== prefix)) {
    fail(path, prefix ? `expected a ${prefix}_ id` : "expected an entity id");
  }
  return value as string;
}

function ids(value: unknown, path: string, max: number, prefix?: string, min = 0): string[] {
  return array(value, path, max, min).map((item, i) => id(item, `${path}[${i}]`, prefix));
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
  if (!allowed.includes(value as T)) fail(path, `expected one of ${allowed.join(", ")}`);
  return value as T;
}

function tag(value: unknown, path: string): string {
  if (typeof value !== "string" || !TAG_RE.test(value)) fail(path, "expected a tag");
  return value;
}

function optional<T>(value: unknown, read: (v: unknown) => T): T | null {
  return value === null || value === undefined ? null : read(value);
}

function timestamp(value: unknown, path: string): string {
  if (typeof value !== "string" || Number.isNaN(Date.parse(value))) fail(path, "expected a timestamp");
  return value;
}

function parseProvenance(value: unknown, path: string): Provenance {
  const p = object(value, path);
  const by = object(p.created_by, `${path}.created_by`);
  if (p.schema_version !== 1) fail(`${path}.schema_version`, "expected 1");
  id(by.actor_id, `${path}.created_by.actor_id`, "act"); // checked, never kept
  return {
    created_by: { kind: oneOf(by.kind, ACTOR_KINDS, `${path}.created_by.kind`) },
    created_at: timestamp(p.created_at, `${path}.created_at`),
    method: oneOf(p.method, DERIVATION_METHODS, `${path}.method`),
    model: parseModelRef(p.model, `${path}.model`),
    derived_from: ids(p.derived_from ?? [], `${path}.derived_from`, 256),
    source_ids: ids(p.source_ids ?? [], `${path}.source_ids`, 256),
    verification_status: oneOf(
      p.verification_status ?? "UNVERIFIED",
      VERIFICATION_STATUSES,
      `${path}.verification_status`,
    ),
    supersedes: optional(p.supersedes, (s) => id(s, `${path}.supersedes`)),
  };
}

export function parseModelRef(value: unknown, path: string): ModelRef | null {
  return optional(value, (m) => {
    const ref = object(m, path);
    return {
      provider: text(ref.provider, `${path}.provider`, 64),
      model_id: text(ref.model_id, `${path}.model_id`, 128),
      prompt_version: text(ref.prompt_version, `${path}.prompt_version`, 64),
      runtime: text(ref.runtime, `${path}.runtime`, 64),
    };
  });
}

export function parseContexts(value: unknown, path: string): string[] {
  return array(value, path, 16, 1).map((c, i) => tag(c, `${path}[${i}]`));
}

/** The fields of an edge both wire formats carry under the same names. */
export function parseEdgeFields(e: Json, path: string) {
  const level = e.epistemic_level;
  if (!Number.isInteger(level) || (level as number) < 0 || (level as number) > 5) {
    fail(`${path}.epistemic_level`, "expected a rung from 0 to 5");
  }
  return {
    edge_id: id(e.edge_id, `${path}.edge_id`, "hyp"),
    relationship: text(e.relationship, `${path}.relationship`),
    status: oneOf(e.status, RELATIONSHIP_STATUSES, `${path}.status`),
    epistemic_level: level as EpistemicLevel,
    support: array(e.support ?? [], `${path}.support`, 512).map((item, i) => {
      const s = object(item, `${path}.support[${i}]`);
      return {
        entity_id: id(s.entity_id, `${path}.support[${i}].entity_id`),
        kind: oneOf(s.kind, SUPPORT_KINDS, `${path}.support[${i}].kind`),
      };
    }),
    counterevidence: ids(e.counterevidence ?? [], `${path}.counterevidence`, 512),
    contradicting_outcomes: ids(e.contradicting_outcomes ?? [], `${path}.contradicting_outcomes`, 128),
    confounders: array(e.confounders ?? [], `${path}.confounders`, 16).map((c, i) =>
      text(c, `${path}.confounders[${i}]`),
    ),
    alternative_explanations: array(
      e.alternative_explanations ?? [],
      `${path}.alternative_explanations`,
      16,
    ).map((a, i) => text(a, `${path}.alternative_explanations[${i}]`)),
    competing_edges: ids(e.competing_edges ?? [], `${path}.competing_edges`, 32, "hyp"),
    experiments: ids(e.experiments ?? [], `${path}.experiments`, 64, "exp"),
    validity: optional(e.validity, (v) => {
      const w = object(v, `${path}.validity`);
      const window = {
        valid_from: timestamp(w.valid_from, `${path}.validity.valid_from`),
        review_after: timestamp(w.review_after, `${path}.validity.review_after`),
      };
      if (Date.parse(window.review_after) <= Date.parse(window.valid_from)) {
        fail(`${path}.validity`, "review_after must be later than valid_from");
      }
      return window;
    }),
    learning_status: optional(e.learning_status, (v) =>
      oneOf(v, LEARNING_STATUSES, `${path}.learning_status`),
    ),
    raw_evidence: ids(e.raw_evidence, `${path}.raw_evidence`, 512, "evd", 1),
  };
}

/**
 * CausalEdge._state_is_consistent, so an illegal state can never reach the
 * map: a link is only drawn as tested if the kernel could hold it.
 */
export function checkEdge(edge: CausalEdge, path: string): CausalEdge {
  if (edge.provenance.derived_from.length === 0 || edge.provenance.source_ids.length === 0) {
    fail(`${path}.provenance`, "an edge requires lineage provenance");
  }
  if (edge.status === "SUPPORTED") {
    if (!edge.support.some((s) => s.kind === "EXPERIMENTAL")) {
      fail(path, "observational support alone cannot make an edge SUPPORTED");
    }
    if (edge.epistemic_level < EpistemicLevel.TESTED_HYPOTHESIS) {
      fail(path, "a SUPPORTED edge must be at least a tested hypothesis");
    }
    if (edge.contradicting_outcomes.length > 0) fail(path, "a contradicted edge cannot be SUPPORTED");
    if (edge.learning_status !== null && !TRUSTED_LEARNING.has(edge.learning_status)) {
      fail(path, "a stale or retest-pending learning cannot back a SUPPORTED edge");
    }
  }
  if (edge.status === "REFUTED" && edge.contradicting_outcomes.length === 0) {
    fail(path, "a REFUTED edge must cite the contradicting outcome");
  }
  if (edge.epistemic_level === EpistemicLevel.CONTEXTUAL_LEARNING && edge.validity === null) {
    fail(path, "a level-5 edge carries its validity window");
  }
  const counter = new Set(edge.counterevidence);
  if (edge.contradicting_outcomes.some((o) => !counter.has(o))) {
    fail(path, "contradicting outcomes are part of the counterevidence");
  }
  return edge;
}

/** A twin whose every edge id appears once. */
export function checkTwin(twin: CausalTwin, path: string): CausalTwin {
  const seen = new Set<string>();
  for (const [i, edge] of twin.edges.entries()) {
    if (seen.has(edge.edge_id)) fail(`${path}.edges[${i}]`, "duplicate edge id");
    seen.add(edge.edge_id);
  }
  return twin;
}

function parseEdge(value: unknown, path: string, childId: string): CausalEdge {
  const e = object(value, path);
  const scope = object(e.scope, `${path}.scope`);
  // The kernel format names the child on every edge and scope: checked, never kept.
  const edgeChild = id(e.child_id, `${path}.child_id`, "chd");
  if (id(scope.child_id, `${path}.scope.child_id`, "chd") !== edgeChild) {
    fail(path, "edge scope must belong to the same child");
  }
  if (edgeChild !== childId) fail(path, "edge belongs to another child");
  const { edge_id, relationship, ...rest } = parseEdgeFields(e, path);
  return checkEdge(
    {
      edge_id,
      relationship,
      cause: optional(e.cause, (v) => tag(v, `${path}.cause`)),
      effect: optional(e.effect, (v) => tag(v, `${path}.effect`)),
      ...rest,
      scope: { contexts: parseContexts(scope.contexts, `${path}.scope.contexts`) },
      provenance: parseProvenance(e.provenance, `${path}.provenance`),
    },
    path,
  );
}

/** Validate an untrusted payload in the kernel's twin format, or throw TwinValidationError. */
export function parseCausalTwin(value: unknown): CausalTwin {
  const t = object(value, "twin");
  if (t.twin_version !== TWIN_VERSION) fail("twin.twin_version", `expected ${TWIN_VERSION}`);
  const childId = id(t.child_id, "twin.child_id", "chd");
  if (typeof t.ledger_head !== "string" || !SHA256_RE.test(t.ledger_head)) {
    fail("twin.ledger_head", "expected a sha256 digest");
  }
  const edges = array(t.edges ?? [], "twin.edges", 1024).map((e, i) =>
    parseEdge(e, `twin.edges[${i}]`, childId),
  );
  return checkTwin({ ledger_head: t.ledger_head, edges }, "twin");
}

/** CausalTwin.variables: every named cause and effect, sorted. */
export function twinVariables(twin: CausalTwin): string[] {
  const names = new Set<string>();
  for (const edge of twin.edges) {
    if (edge.cause !== null) names.add(edge.cause);
    if (edge.effect !== null) names.add(edge.effect);
  }
  return [...names].sort();
}
