// The Causal Twin provenance projection as the kernel serializes it:
// `TwinProvenanceView.model_dump(mode="json")` from serene/causal/provenance.py
// (Issue #75). Field names and enums mirror the Pydantic models exactly.
//
// It carries what the twin itself does not: what each cited item says (its
// display text, never raw evidence content), when it was recorded, whether its
// evidence came from the family or from outside, each experiment's status and
// outcomes, the full lineage of every link, and why a link was replaced or
// refuted. It holds no child, actor or source ids.
//
// As with the twin, the web app never decides what any of it means:
// `parseTwinProvenance` re-checks the kernel's invariants and fails closed,
// and `pairWithTwin` refuses a projection built from a different ledger
// position than the map it would explain.

import { wireReader } from "@/lib/wire";
import {
  TwinValidationError,
  type ActorKind,
  type CausalTwin,
  type DerivationMethod,
  type EpistemicLevel,
  type LearningStatus,
  type ModelRef,
  type RelationshipStatus,
  type SupportKind,
  type ValidityWindow,
  type VerificationStatus,
} from "./model";

export const PROVENANCE_VERSION = "causal-twin-provenance/1";

export type NodeKind =
  | "EVIDENCE"
  | "OBSERVATION"
  | "PATTERN"
  | "HYPOTHESIS"
  | "INVESTIGATION"
  | "EXPERIMENT"
  | "TRIAL"
  | "OUTCOME"
  | "LEARNING"
  | "OTHER";
export type EvidenceOrigin = "FAMILY" | "EXTERNAL" | "MIXED" | "UNRESOLVED";
export type LifecycleStatus = "ACTIVE" | "SUPERSEDED" | "REFUTED";
export type EvidenceKind = "PARENT_REPORT" | "CAREGIVER_REPORT" | "DOCUMENT" | "BROWSER_CAPTURE";
export type SourceKind = "TELEGRAM" | "WEB_APP" | "BROWSER" | "EXTERNAL_DOCUMENT" | "KERNEL" | "EVAL_FIXTURE";
export type ExperimentStatus =
  | "PROPOSED"
  | "CLASSIFIED"
  | "BLOCKED"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "STARTED"
  | "COMPLETED"
  | "ABANDONED"
  | "PARKED_UNRESOLVED";
export type SafetyClass = "GREEN" | "AMBER" | "RED";
export type OutcomeResult = "SUPPORTS" | "CONTRADICTS" | "INCONCLUSIVE";

export type NodeOrigin = {
  actor_kind: ActorKind;
  method: DerivationMethod;
  model: ModelRef | null;
  created_at: string;
  derived_from: readonly string[];
  source_ids: readonly string[];
  supersedes: string | null;
};

export type RawEvidenceDetail = {
  evidence_kind: EvidenceKind;
  source_kind: SourceKind;
  external: boolean;
  source_host: string | null;
  captured_at: string;
  retrieved_at: string | null;
  content_digest: string;
  checks_passed: readonly string[];
  rejection_reason_codes: readonly string[];
};

export type ProvenanceNode = {
  entity_id: string;
  kind: NodeKind;
  epistemic_level: EpistemicLevel | null;
  verification_status: VerificationStatus;
  lifecycle: LifecycleStatus;
  superseded_by: string | null;
  summary: string;
  occurred_at: string;
  origin: NodeOrigin;
  evidence: RawEvidenceDetail | null;
  parents: readonly string[];
  raw_evidence: readonly string[];
  missing: readonly string[];
  evidence_origin: EvidenceOrigin;
};

export type MissingNode = { entity_id: string; referenced_by: readonly string[] };
export type LineageStep = { entity_id: string; depth: number };
export type EdgeLineage = {
  root: string;
  steps: readonly LineageStep[];
  raw_evidence: readonly string[];
  missing: readonly MissingNode[];
  complete: boolean;
};

export type OutcomeProvenance = {
  outcome_id: string;
  experiment_id: string;
  result: OutcomeResult;
  reported_at: string;
  summary: string;
};

export type ExperimentProvenance = {
  experiment_id: string;
  status: ExperimentStatus;
  safety_class: SafetyClass | null;
  intervention: string;
  outcome_measure: string;
  started_at: string | null;
  ended_at: string | null;
  outcomes: readonly OutcomeProvenance[];
};

export type SupersessionDetail = { superseded_by: string | null; reason: string | null; supersedes: string | null };
export type RefutationDetail = { reason_codes: readonly string[]; outcome_ids: readonly string[] };

export type LearningProvenance = {
  learning_id: string;
  statement: string;
  recorded_status: LearningStatus;
  effective_status: LearningStatus;
  review_due: boolean;
  scope_contexts: readonly string[];
  valid_from: string;
  review_after: string;
  status_changed_at: string | null;
  reviewer_kind: ActorKind;
  retest_triggers: readonly string[];
  experiment_ids: readonly string[];
  outcome_ids: readonly string[];
  confounders: readonly string[];
  counterevidence: readonly string[];
  superseded_learnings: readonly string[];
};

export type EdgeProvenance = {
  edge_id: string;
  relationship: string;
  status: RelationshipStatus;
  lifecycle: LifecycleStatus;
  epistemic_level: EpistemicLevel;
  verification_status: VerificationStatus;
  learning_status: LearningStatus | null;
  scope_contexts: readonly string[];
  validity: ValidityWindow | null;
  confounders: readonly string[];
  alternative_explanations: readonly string[];
  competing_edges: readonly string[];
  support: readonly { entity_id: string; kind: SupportKind }[];
  counterevidence: readonly { entity_id: string; contradicting_outcome: boolean }[];
  experiments: readonly ExperimentProvenance[];
  learning: LearningProvenance | null;
  supersession: SupersessionDetail;
  refutation: RefutationDetail | null;
  origin: NodeOrigin;
  lineage: EdgeLineage;
};

export type TwinProvenance = {
  version: typeof PROVENANCE_VERSION;
  ledger_head: string;
  as_of: string;
  nodes: ReadonlyMap<string, ProvenanceNode>;
  missing: ReadonlyMap<string, MissingNode>;
  edges: ReadonlyMap<string, EdgeProvenance>;
};

const NODE_KINDS: readonly NodeKind[] = [
  "EVIDENCE", "OBSERVATION", "PATTERN", "HYPOTHESIS", "INVESTIGATION",
  "EXPERIMENT", "TRIAL", "OUTCOME", "LEARNING", "OTHER",
];
const ORIGINS: readonly EvidenceOrigin[] = ["FAMILY", "EXTERNAL", "MIXED", "UNRESOLVED"];
const LIFECYCLES: readonly LifecycleStatus[] = ["ACTIVE", "SUPERSEDED", "REFUTED"];
const EVIDENCE_KINDS: readonly EvidenceKind[] = ["PARENT_REPORT", "CAREGIVER_REPORT", "DOCUMENT", "BROWSER_CAPTURE"];
const SOURCE_KINDS: readonly SourceKind[] = ["TELEGRAM", "WEB_APP", "BROWSER", "EXTERNAL_DOCUMENT", "KERNEL", "EVAL_FIXTURE"];
const EXTERNAL_SOURCES: ReadonlySet<SourceKind> = new Set(["BROWSER", "EXTERNAL_DOCUMENT"]);
const EXPERIMENT_STATUSES: readonly ExperimentStatus[] = [
  "PROPOSED", "CLASSIFIED", "BLOCKED", "AWAITING_APPROVAL", "APPROVED",
  "STARTED", "COMPLETED", "ABANDONED", "PARKED_UNRESOLVED",
];
const SAFETY_CLASSES: readonly SafetyClass[] = ["GREEN", "AMBER", "RED"];
const RESULTS: readonly OutcomeResult[] = ["SUPPORTS", "CONTRADICTS", "INCONCLUSIVE"];
const STATUSES: readonly RelationshipStatus[] = ["CANDIDATE", "SUPPORTED", "REFUTED", "SUPERSEDED"];
const SUPPORT_KINDS: readonly SupportKind[] = ["OBSERVATIONAL", "EXPERIMENTAL"];
const LEARNING_STATUSES: readonly LearningStatus[] = ["ACTIVE", "NEEDS_REVIEW", "NEEDS_RETEST", "STALE", "DEPRECATED"];
const ACTOR_KINDS: readonly ActorKind[] = [
  "PARENT", "CAREGIVER", "AGENT", "POLICY", "VERIFIER", "SYSTEM", "MEMORY_COMMITTER",
];
const METHODS: readonly DerivationMethod[] = [
  "PARENT_REPORT", "CAREGIVER_REPORT", "BROWSER_ACQUISITION", "MODEL_EXTRACTION",
  "MODEL_INFERENCE", "DETERMINISTIC_RULE", "EXPERIMENT_OUTCOME", "HUMAN_REVIEW",
];
const VERIFICATIONS: readonly VerificationStatus[] = ["UNVERIFIED", "VERIFIED", "REJECTED", "NOT_APPLICABLE"];
// Family identifiers: the projection must never carry them (serene/causal/provenance.py).
const FAMILY_PREFIXES = new Set(["chd", "act", "src"]);

function fail(path: string, problem: string): never {
  throw new TwinValidationError(`${path}: ${problem}`);
}
const r = wireReader(fail);

function entityId(value: unknown, path: string, prefix?: string): string {
  const id = r.id(value, path, prefix);
  if (FAMILY_PREFIXES.has(id.slice(0, 3))) fail(path, "a family identifier is not allowed here");
  return id;
}
function entityIds(value: unknown, path: string, max: number, prefix?: string, min = 0): string[] {
  return r.array(value, path, max, min).map((v, i) => entityId(v, `${path}[${i}]`, prefix));
}
function texts(value: unknown, path: string, max: number): string[] {
  return r.array(value, path, max).map((t, i) => r.text(t, `${path}[${i}]`));
}
function level(value: unknown, path: string): EpistemicLevel {
  return r.integer(value, path, 0, 5) as EpistemicLevel;
}
function tags(value: unknown, path: string): string[] {
  return r.array(value, path, 16, 1).map((t, i) => r.tag(t, `${path}[${i}]`));
}

function parseOrigin(value: unknown, path: string): NodeOrigin {
  const o = r.object(value, path);
  return {
    actor_kind: r.oneOf(o.actor_kind, ACTOR_KINDS, `${path}.actor_kind`),
    method: r.oneOf(o.method, METHODS, `${path}.method`),
    model: r.optional(o.model, (m) => {
      const ref = r.object(m, `${path}.model`);
      return {
        provider: r.text(ref.provider, `${path}.model.provider`, 64),
        model_id: r.text(ref.model_id, `${path}.model.model_id`, 128),
        prompt_version: r.text(ref.prompt_version, `${path}.model.prompt_version`, 64),
        runtime: r.text(ref.runtime, `${path}.model.runtime`, 64),
      };
    }),
    created_at: r.timestamp(o.created_at, `${path}.created_at`),
    derived_from: entityIds(o.derived_from, `${path}.derived_from`, 256),
    source_ids: entityIds(o.source_ids, `${path}.source_ids`, 256),
    supersedes: r.optional(o.supersedes, (s) => entityId(s, `${path}.supersedes`)),
  };
}

function parseEvidence(value: unknown, path: string): RawEvidenceDetail {
  const e = r.object(value, path);
  const detail: RawEvidenceDetail = {
    evidence_kind: r.oneOf(e.evidence_kind, EVIDENCE_KINDS, `${path}.evidence_kind`),
    source_kind: r.oneOf(e.source_kind, SOURCE_KINDS, `${path}.source_kind`),
    external: r.bool(e.external, `${path}.external`),
    source_host: r.optional(e.source_host, (h) => r.text(h, `${path}.source_host`, 253)),
    captured_at: r.timestamp(e.captured_at, `${path}.captured_at`),
    retrieved_at: r.optional(e.retrieved_at, (t) => r.timestamp(t, `${path}.retrieved_at`)),
    content_digest: r.sha256(e.content_digest, `${path}.content_digest`),
    checks_passed: r.reasons(e.checks_passed, `${path}.checks_passed`, 16),
    rejection_reason_codes: r.reasons(e.rejection_reason_codes, `${path}.rejection_reason_codes`, 32),
  };
  if (detail.external !== EXTERNAL_SOURCES.has(detail.source_kind)) {
    fail(path, "external evidence is exactly evidence from an external source");
  }
  if (detail.source_host !== null && !detail.external) fail(path, "only an external source names its host");
  return detail;
}

function parseNode(value: unknown, path: string): ProvenanceNode {
  const n = r.object(value, path);
  const node: ProvenanceNode = {
    entity_id: entityId(n.entity_id, `${path}.entity_id`),
    kind: r.oneOf(n.kind, NODE_KINDS, `${path}.kind`),
    epistemic_level: r.optional(n.epistemic_level, (v) => level(v, `${path}.epistemic_level`)),
    verification_status: r.oneOf(n.verification_status, VERIFICATIONS, `${path}.verification_status`),
    lifecycle: r.oneOf(n.lifecycle, LIFECYCLES, `${path}.lifecycle`),
    superseded_by: r.optional(n.superseded_by, (s) => entityId(s, `${path}.superseded_by`)),
    summary: r.text(n.summary, `${path}.summary`),
    occurred_at: r.timestamp(n.occurred_at, `${path}.occurred_at`),
    origin: parseOrigin(n.origin, `${path}.origin`),
    evidence: r.optional(n.evidence, (e) => parseEvidence(e, `${path}.evidence`)),
    parents: entityIds(n.parents, `${path}.parents`, 256),
    raw_evidence: entityIds(n.raw_evidence, `${path}.raw_evidence`, 1024, "evd"),
    missing: entityIds(n.missing, `${path}.missing`, 1024),
    evidence_origin: r.oneOf(n.evidence_origin, ORIGINS, `${path}.evidence_origin`),
  };
  if ((node.kind === "EVIDENCE") !== (node.evidence !== null)) {
    fail(path, "evidence detail is present exactly on raw evidence");
  }
  if (node.kind === "EVIDENCE" && (node.parents.length > 0 || node.raw_evidence.join() !== node.entity_id)) {
    fail(path, "raw evidence has no parents and rests on itself");
  }
  if ((node.evidence_origin === "UNRESOLVED") !== (node.raw_evidence.length === 0)) {
    fail(path, "an item's origin is unresolved exactly when no evidence is reached");
  }
  return node;
}

function parseMissing(value: unknown, path: string): MissingNode {
  const m = r.object(value, path);
  return {
    entity_id: entityId(m.entity_id, `${path}.entity_id`),
    referenced_by: entityIds(m.referenced_by, `${path}.referenced_by`, 1024, undefined, 1),
  };
}

function parseLineage(value: unknown, path: string): EdgeLineage {
  const l = r.object(value, path);
  const lineage: EdgeLineage = {
    root: entityId(l.root, `${path}.root`, "hyp"),
    steps: r.array(l.steps, `${path}.steps`, 4096).map((s, i) => {
      const step = r.object(s, `${path}.steps[${i}]`);
      return {
        entity_id: entityId(step.entity_id, `${path}.steps[${i}].entity_id`),
        depth: r.integer(step.depth, `${path}.steps[${i}].depth`, 0, 64),
      };
    }),
    raw_evidence: entityIds(l.raw_evidence, `${path}.raw_evidence`, 1024, "evd"),
    missing: r.array(l.missing, `${path}.missing`, 1024).map((m, i) => parseMissing(m, `${path}.missing[${i}]`)),
    complete: r.bool(l.complete, `${path}.complete`),
  };
  if (lineage.complete !== (lineage.missing.length === 0 && lineage.raw_evidence.length > 0)) {
    fail(path, "a lineage is complete when it has no gaps and reaches evidence");
  }
  const onChain = new Set(lineage.steps.map((s) => s.entity_id));
  if (lineage.raw_evidence.some((e) => !onChain.has(e))) fail(path, "raw evidence of a lineage lies on it");
  for (let i = 1; i < lineage.steps.length; i++) {
    if (lineage.steps[i].depth < lineage.steps[i - 1].depth) fail(`${path}.steps`, "steps are ordered nearest first");
  }
  return lineage;
}

function parseExperiment(value: unknown, path: string): ExperimentProvenance {
  const x = r.object(value, path);
  const experiment: ExperimentProvenance = {
    experiment_id: entityId(x.experiment_id, `${path}.experiment_id`, "exp"),
    status: r.oneOf(x.status, EXPERIMENT_STATUSES, `${path}.status`),
    safety_class: r.optional(x.safety_class, (c) => r.oneOf(c, SAFETY_CLASSES, `${path}.safety_class`)),
    intervention: r.text(x.intervention, `${path}.intervention`),
    outcome_measure: r.text(x.outcome_measure, `${path}.outcome_measure`),
    started_at: r.optional(x.started_at, (t) => r.timestamp(t, `${path}.started_at`)),
    ended_at: r.optional(x.ended_at, (t) => r.timestamp(t, `${path}.ended_at`)),
    outcomes: r.array(x.outcomes, `${path}.outcomes`, 64).map((o, i) => {
      const p = `${path}.outcomes[${i}]`;
      const out = r.object(o, p);
      return {
        outcome_id: entityId(out.outcome_id, `${p}.outcome_id`, "out"),
        experiment_id: entityId(out.experiment_id, `${p}.experiment_id`, "exp"),
        result: r.oneOf(out.result, RESULTS, `${p}.result`),
        reported_at: r.timestamp(out.reported_at, `${p}.reported_at`),
        summary: r.text(out.summary, `${p}.summary`),
      };
    }),
  };
  if (experiment.outcomes.some((o) => o.experiment_id !== experiment.experiment_id)) {
    fail(path, "an experiment lists only its own outcomes");
  }
  return experiment;
}

function parseLearning(value: unknown, path: string): LearningProvenance {
  const l = r.object(value, path);
  return {
    learning_id: entityId(l.learning_id, `${path}.learning_id`, "lrn"),
    statement: r.text(l.statement, `${path}.statement`),
    recorded_status: r.oneOf(l.recorded_status, LEARNING_STATUSES, `${path}.recorded_status`),
    effective_status: r.oneOf(l.effective_status, LEARNING_STATUSES, `${path}.effective_status`),
    review_due: r.bool(l.review_due, `${path}.review_due`),
    scope_contexts: tags(l.scope_contexts, `${path}.scope_contexts`),
    valid_from: r.timestamp(l.valid_from, `${path}.valid_from`),
    review_after: r.timestamp(l.review_after, `${path}.review_after`),
    status_changed_at: r.optional(l.status_changed_at, (t) => r.timestamp(t, `${path}.status_changed_at`)),
    reviewer_kind: r.oneOf(l.reviewer_kind, ACTOR_KINDS, `${path}.reviewer_kind`),
    retest_triggers: texts(l.retest_triggers, `${path}.retest_triggers`, 8),
    experiment_ids: entityIds(l.experiment_ids, `${path}.experiment_ids`, 16, "exp"),
    outcome_ids: entityIds(l.outcome_ids, `${path}.outcome_ids`, 64, "out"),
    confounders: texts(l.confounders, `${path}.confounders`, 16),
    counterevidence: entityIds(l.counterevidence, `${path}.counterevidence`, 512),
    superseded_learnings: entityIds(l.superseded_learnings, `${path}.superseded_learnings`, 64, "lrn"),
  };
}

function parseEdge(value: unknown, path: string): EdgeProvenance {
  const e = r.object(value, path);
  const s = r.object(e.supersession, `${path}.supersession`);
  const edge: EdgeProvenance = {
    edge_id: entityId(e.edge_id, `${path}.edge_id`, "hyp"),
    relationship: r.text(e.relationship, `${path}.relationship`),
    status: r.oneOf(e.status, STATUSES, `${path}.status`),
    lifecycle: r.oneOf(e.lifecycle, LIFECYCLES, `${path}.lifecycle`),
    epistemic_level: level(e.epistemic_level, `${path}.epistemic_level`),
    verification_status: r.oneOf(e.verification_status, VERIFICATIONS, `${path}.verification_status`),
    learning_status: r.optional(e.learning_status, (v) => r.oneOf(v, LEARNING_STATUSES, `${path}.learning_status`)),
    scope_contexts: tags(e.scope_contexts, `${path}.scope_contexts`),
    validity: r.optional(e.validity, (v) => {
      const w = r.object(v, `${path}.validity`);
      return {
        valid_from: r.timestamp(w.valid_from, `${path}.validity.valid_from`),
        review_after: r.timestamp(w.review_after, `${path}.validity.review_after`),
      };
    }),
    confounders: texts(e.confounders, `${path}.confounders`, 16),
    alternative_explanations: texts(e.alternative_explanations, `${path}.alternative_explanations`, 16),
    competing_edges: entityIds(e.competing_edges, `${path}.competing_edges`, 32, "hyp"),
    support: r.array(e.support, `${path}.support`, 512).map((item, i) => {
      const it = r.object(item, `${path}.support[${i}]`);
      return {
        entity_id: entityId(it.entity_id, `${path}.support[${i}].entity_id`),
        kind: r.oneOf(it.kind, SUPPORT_KINDS, `${path}.support[${i}].kind`),
      };
    }),
    counterevidence: r.array(e.counterevidence, `${path}.counterevidence`, 512).map((item, i) => {
      const it = r.object(item, `${path}.counterevidence[${i}]`);
      return {
        entity_id: entityId(it.entity_id, `${path}.counterevidence[${i}].entity_id`),
        contradicting_outcome: r.bool(it.contradicting_outcome, `${path}.counterevidence[${i}].contradicting_outcome`),
      };
    }),
    experiments: r.array(e.experiments, `${path}.experiments`, 64).map((x, i) => parseExperiment(x, `${path}.experiments[${i}]`)),
    learning: r.optional(e.learning, (l) => parseLearning(l, `${path}.learning`)),
    supersession: {
      superseded_by: r.optional(s.superseded_by, (v) => entityId(v, `${path}.supersession.superseded_by`, "hyp")),
      reason: r.optional(s.reason, (v) => r.text(v, `${path}.supersession.reason`)),
      supersedes: r.optional(s.supersedes, (v) => entityId(v, `${path}.supersession.supersedes`)),
    },
    refutation: r.optional(e.refutation, (v) => {
      const f = r.object(v, `${path}.refutation`);
      return {
        reason_codes: r.reasons(f.reason_codes, `${path}.refutation.reason_codes`, 32, 1),
        outcome_ids: entityIds(f.outcome_ids, `${path}.refutation.outcome_ids`, 128, "out", 1),
      };
    }),
    origin: parseOrigin(e.origin, `${path}.origin`),
    lineage: parseLineage(e.lineage, `${path}.lineage`),
  };
  // EdgeProvenance._state_is_explained
  if (edge.lineage.root !== edge.edge_id) fail(path, "an edge's lineage starts at the edge");
  if (edge.epistemic_level === 5 && (edge.learning === null || edge.validity === null)) {
    fail(path, "a level-5 edge carries its learning and validity window");
  }
  if ((edge.lifecycle === "REFUTED") !== (edge.refutation !== null)) {
    fail(path, "refutation detail is present exactly on a refuted edge");
  }
  if ((edge.lifecycle === "SUPERSEDED") !== (edge.supersession.superseded_by !== null)) {
    fail(path, "supersession detail is present exactly on a superseded edge");
  }
  if ((edge.supersession.superseded_by === null) !== (edge.supersession.reason === null)) {
    fail(path, "a replaced edge carries its supersession reason");
  }
  return edge;
}

/** Every entity id an edge's projection points at (EdgeProvenance.cited_ids). */
export function citedIds(edge: EdgeProvenance): Set<string> {
  const ids = new Set<string>([edge.edge_id]);
  const add = (list: readonly string[]) => list.forEach((id) => ids.add(id));
  add(edge.support.map((s) => s.entity_id));
  add(edge.counterevidence.map((c) => c.entity_id));
  add(edge.lineage.steps.map((s) => s.entity_id));
  add(edge.lineage.raw_evidence);
  for (const x of edge.experiments) {
    ids.add(x.experiment_id);
    add(x.outcomes.map((o) => o.outcome_id));
  }
  if (edge.learning) {
    ids.add(edge.learning.learning_id);
    add(edge.learning.outcome_ids);
    add(edge.learning.experiment_ids);
  }
  if (edge.refutation) add(edge.refutation.outcome_ids);
  add(edge.origin.derived_from);
  add(edge.origin.source_ids);
  return ids;
}

/** Validate an untrusted payload as a provenance projection, or throw TwinValidationError. */
export function parseTwinProvenance(value: unknown): TwinProvenance {
  const v = r.object(value, "provenance");
  if (v.version !== PROVENANCE_VERSION) fail("provenance.version", `expected ${PROVENANCE_VERSION}`);
  const nodes = new Map<string, ProvenanceNode>();
  r.array(v.nodes, "provenance.nodes", 16384).forEach((n, i) => {
    const node = parseNode(n, `provenance.nodes[${i}]`);
    if (nodes.has(node.entity_id)) fail(`provenance.nodes[${i}]`, "duplicate node");
    nodes.set(node.entity_id, node);
  });
  const missing = new Map<string, MissingNode>();
  r.array(v.missing, "provenance.missing", 16384).forEach((m, i) => {
    const gap = parseMissing(m, `provenance.missing[${i}]`);
    if (nodes.has(gap.entity_id) || missing.has(gap.entity_id)) fail(`provenance.missing[${i}]`, "each id is one node or one missing entry");
    missing.set(gap.entity_id, gap);
  });
  const edges = new Map<string, EdgeProvenance>();
  r.array(v.edges, "provenance.edges", 1024).forEach((e, i) => {
    const edge = parseEdge(e, `provenance.edges[${i}]`);
    if (edges.has(edge.edge_id)) fail(`provenance.edges[${i}]`, "duplicate edge");
    edges.set(edge.edge_id, edge);
  });
  // TwinProvenanceView._every_link_resolves: a link the panel follows always lands.
  const referenced = new Set<string>();
  for (const node of nodes.values()) {
    [...node.parents, ...node.raw_evidence, ...node.missing].forEach((id) => referenced.add(id));
  }
  for (const edge of edges.values()) {
    citedIds(edge).forEach((id) => referenced.add(id));
    edge.lineage.missing.forEach((m) => referenced.add(m.entity_id));
  }
  const unresolved = [...referenced].filter((id) => !nodes.has(id) && !missing.has(id)).sort();
  if (unresolved.length > 0) fail("provenance", `unresolved provenance ids: ${unresolved.join(", ")}`);
  return {
    version: PROVENANCE_VERSION,
    ledger_head: r.sha256(v.ledger_head, "provenance.ledger_head"),
    as_of: r.timestamp(v.as_of, "provenance.as_of"),
    nodes,
    missing,
    edges,
  };
}

/**
 * Accept a provenance projection only for the exact twin it explains: same
 * ledger position, same links, same verdicts.
 */
export function pairWithTwin(twin: CausalTwin, provenance: TwinProvenance): TwinProvenance {
  if (provenance.ledger_head !== twin.ledger_head) fail("provenance.ledger_head", "built from another ledger position");
  if (provenance.edges.size !== twin.edges.length) fail("provenance.edges", "does not match the twin's links");
  for (const edge of twin.edges) {
    const detail = provenance.edges.get(edge.edge_id);
    if (!detail) fail("provenance.edges", `no provenance for ${edge.edge_id}`);
    if (detail.status !== edge.status || detail.epistemic_level !== edge.epistemic_level) {
      fail(`provenance.edges.${edge.edge_id}`, "verdict differs from the twin");
    }
    if (detail.lineage.raw_evidence.join() !== edge.raw_evidence.join()) {
      fail(`provenance.edges.${edge.edge_id}`, "lineage differs from the twin");
    }
  }
  return provenance;
}
