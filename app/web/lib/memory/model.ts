import type {
  ActorKind,
  DerivationMethod,
  EpistemicLevel,
  LearningStatus,
  ModelRef,
  VerificationStatus,
} from "@/lib/causal-twin/model";
import { wireReader } from "@/lib/wire";

// Consolidated memory and Dream runs as the kernel serializes them:
// `MemoryDreamView.model_dump(mode="json")` from serene/memory/view.py
// (Issue #36). Field names and enums mirror the Pydantic models exactly.
//
// The view is read-only. Nothing here can propose, commit or edit memory;
// the surface only shows what the ledger already decided and why.
// `parseMemoryDreamView` re-checks the kernel's own invariants and rejects
// anything else, so a rejected patch can never be drawn without its reasons.

export const VIEW_VERSION = "memory-dream-view/1";

export type PatchStatus = "PROPOSED" | "COMMITTED" | "REJECTED";
export type MemoryOperation = "CREATE" | "UPDATE" | "DEPRECATE";
export type MemoryCheck = "DOCUMENT_FORMAT" | "CONTRADICTION_SEARCH" | "LINEAGE" | "PROMOTION_GATE";
export type DreamStage = "ORIENT" | "CONSOLIDATE" | "REFLECT" | "CHALLENGE" | "VERIFY" | "PROPOSE_PATCH";
export type MemoryKind =
  | "learning"
  | "routine"
  | "pattern"
  | "child_fact"
  | "caregiver"
  | "investigation"
  | "decision";

export type LineageNode = {
  entity_id: string;
  level: EpistemicLevel | null;
  verification_status: VerificationStatus;
  parents: readonly string[];
};

export type Lineage = {
  root: string;
  nodes: readonly LineageNode[];
  raw_evidence: readonly string[];
  missing: readonly string[];
};

export type PatchOrigin = {
  actor_kind: ActorKind;
  method: DerivationMethod;
  model: ModelRef | null;
  created_at: string;
  derived_from: readonly string[];
  source_ids: readonly string[];
};

export type PatchReview = {
  passed: boolean;
  checks_passed: readonly MemoryCheck[];
  reason_codes: readonly string[];
  recorded_at: string | null;
};

export type Patch = {
  patch_id: string;
  target_path: string;
  operation: MemoryOperation;
  required_level: EpistemicLevel;
  rationale: string;
  diff: string;
  origin: PatchOrigin;
  status: PatchStatus;
  dream_run_id: string | null;
  review: PatchReview | null;
  decided_at: string | null;
  rejection_reasons: readonly string[];
  commit_sha: string | null;
};

export type DreamStageRecord = {
  stage: DreamStage;
  recorded_at: string;
  item_count: number;
  reason_codes: readonly string[];
};

export type DreamRun = {
  run_id: string;
  started_at: string;
  stages: readonly DreamStageRecord[];
  complete: boolean;
  proposed: readonly string[];
};

export type MemoryItem = {
  path: string;
  kind: MemoryKind;
  title: string;
  body: string;
  subject: string;
  level: EpistemicLevel | null;
  status: LearningStatus;
  scope: readonly string[];
  valid_from: string | null;
  review_after: string | null;
  sources: readonly string[];
  counterevidence: readonly string[];
  revision: string;
  written_by: string | null;
  lineage: Lineage;
};

export type UnreadableMemory = { path: string; revision: string };

export type MemoryDreamView = {
  version: typeof VIEW_VERSION;
  ledger_head: string;
  memory_head: string;
  memories: readonly MemoryItem[];
  unreadable: readonly UnreadableMemory[];
  dream_runs: readonly DreamRun[];
  patches: readonly Patch[];
};

export class MemoryValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MemoryValidationError";
  }
}

function fail(path: string, problem: string): never {
  throw new MemoryValidationError(`${path}: ${problem}`);
}
const r = wireReader(fail);

export const DREAM_STAGES: readonly DreamStage[] = [
  "ORIENT",
  "CONSOLIDATE",
  "REFLECT",
  "CHALLENGE",
  "VERIFY",
  "PROPOSE_PATCH",
];
const PATCH_STATUSES: readonly PatchStatus[] = ["PROPOSED", "COMMITTED", "REJECTED"];
const OPERATIONS: readonly MemoryOperation[] = ["CREATE", "UPDATE", "DEPRECATE"];
const CHECKS: readonly MemoryCheck[] = ["DOCUMENT_FORMAT", "CONTRADICTION_SEARCH", "LINEAGE", "PROMOTION_GATE"];
const MEMORY_KINDS: readonly MemoryKind[] = [
  "learning",
  "routine",
  "pattern",
  "child_fact",
  "caregiver",
  "investigation",
  "decision",
];
const LEARNING_STATUSES: readonly LearningStatus[] = ["ACTIVE", "NEEDS_REVIEW", "NEEDS_RETEST", "STALE", "DEPRECATED"];
const ACTOR_KINDS: readonly ActorKind[] = [
  "PARENT",
  "CAREGIVER",
  "AGENT",
  "POLICY",
  "VERIFIER",
  "SYSTEM",
  "MEMORY_COMMITTER",
];
const METHODS: readonly DerivationMethod[] = [
  "PARENT_REPORT",
  "CAREGIVER_REPORT",
  "BROWSER_ACQUISITION",
  "MODEL_EXTRACTION",
  "MODEL_INFERENCE",
  "DETERMINISTIC_RULE",
  "EXPERIMENT_OUTCOME",
  "HUMAN_REVIEW",
];
const VERIFICATION: readonly VerificationStatus[] = ["UNVERIFIED", "VERIFIED", "REJECTED", "NOT_APPLICABLE"];
// serene.domain.entities.MemoryPath
const MEMORY_PATH_RE =
  /^(child|caregivers|routines|patterns|investigations|decisions|learnings)\/[a-z0-9][a-z0-9_-]{0,63}\.md$/;

function level(value: unknown, path: string): EpistemicLevel {
  return r.integer(value, path, 0, 5) as EpistemicLevel;
}

function parseModel(value: unknown, path: string): ModelRef {
  const m = r.object(value, path);
  return {
    provider: r.text(m.provider, `${path}.provider`, 64),
    model_id: r.text(m.model_id, `${path}.model_id`, 128),
    prompt_version: r.text(m.prompt_version, `${path}.prompt_version`, 64),
    runtime: r.text(m.runtime, `${path}.runtime`, 64),
  };
}

function memoryPath(value: unknown, path: string): string {
  const p = r.text(value, path);
  if (!MEMORY_PATH_RE.test(p)) fail(path, "expected a memory path");
  return p;
}

function parseLineage(value: unknown, path: string): Lineage {
  const l = r.object(value, path);
  const nodes = r.array(l.nodes, `${path}.nodes`, 4096).map((n, i) => {
    const node = r.object(n, `${path}.nodes[${i}]`);
    return {
      entity_id: r.id(node.entity_id, `${path}.nodes[${i}].entity_id`),
      level: r.optional(node.level, (v) => level(v, `${path}.nodes[${i}].level`)),
      verification_status: r.oneOf(node.verification_status, VERIFICATION, `${path}.nodes[${i}].verification_status`),
      parents: r.ids(node.parents, `${path}.nodes[${i}].parents`, 256),
    };
  });
  const lineage: Lineage = {
    root: r.id(l.root, `${path}.root`),
    nodes,
    raw_evidence: r.ids(l.raw_evidence, `${path}.raw_evidence`, 4096, "evd"),
    missing: r.ids(l.missing, `${path}.missing`, 4096),
  };
  // trace_lineage: the root and every raw-evidence id are nodes of the trace,
  // and a parent is either a node or reported missing. Nothing dangles.
  const known = new Set(nodes.map((n) => n.entity_id));
  const missing = new Set(lineage.missing);
  if (!known.has(lineage.root) && !missing.has(lineage.root)) fail(path, "the root is not in the trace");
  if (lineage.raw_evidence.some((e) => !known.has(e))) fail(path, "raw evidence must be a node of the trace");
  for (const node of nodes) {
    if (node.parents.some((p) => !known.has(p) && !missing.has(p))) {
      fail(path, `a parent of ${node.entity_id} is neither traced nor reported missing`);
    }
  }
  return lineage;
}

function parsePatch(value: unknown, path: string): Patch {
  const p = r.object(value, path);
  const o = r.object(p.origin, `${path}.origin`);
  const patch: Patch = {
    patch_id: r.id(p.patch_id, `${path}.patch_id`, "mpt"),
    target_path: memoryPath(p.target_path, `${path}.target_path`),
    operation: r.oneOf(p.operation, OPERATIONS, `${path}.operation`),
    required_level: level(p.required_level, `${path}.required_level`),
    rationale: r.text(p.rationale, `${path}.rationale`),
    diff: r.text(p.diff, `${path}.diff`, 20000),
    origin: {
      actor_kind: r.oneOf(o.actor_kind, ACTOR_KINDS, `${path}.origin.actor_kind`),
      method: r.oneOf(o.method, METHODS, `${path}.origin.method`),
      model: r.optional(o.model, (m) => parseModel(m, `${path}.origin.model`)),
      created_at: r.timestamp(o.created_at, `${path}.origin.created_at`),
      derived_from: r.ids(o.derived_from, `${path}.origin.derived_from`, 256),
      source_ids: r.ids(o.source_ids, `${path}.origin.source_ids`, 256),
    },
    status: r.oneOf(p.status, PATCH_STATUSES, `${path}.status`),
    dream_run_id: r.optional(p.dream_run_id, (v) => r.sha256(v, `${path}.dream_run_id`)),
    review: r.optional(p.review, (v) => {
      const rv = r.object(v, `${path}.review`);
      return {
        passed: r.bool(rv.passed, `${path}.review.passed`),
        checks_passed: r
          .array(rv.checks_passed, `${path}.review.checks_passed`, 8)
          .map((c, i) => r.oneOf(c, CHECKS, `${path}.review.checks_passed[${i}]`)),
        reason_codes: r.reasons(rv.reason_codes, `${path}.review.reason_codes`, 64, 1),
        recorded_at: r.optional(rv.recorded_at, (t) => r.timestamp(t, `${path}.review.recorded_at`)),
      };
    }),
    decided_at: r.optional(p.decided_at, (v) => r.timestamp(v, `${path}.decided_at`)),
    rejection_reasons: r.reasons(p.rejection_reasons, `${path}.rejection_reasons`, 64),
    commit_sha: r.optional(p.commit_sha, (v) => r.gitSha(v, `${path}.commit_sha`)),
  };
  // PatchView._decision_is_explained
  if (patch.status === "REJECTED" && patch.rejection_reasons.length === 0) {
    fail(path, "a rejected patch must carry its rejection reasons");
  }
  if (patch.status !== "REJECTED" && patch.rejection_reasons.length > 0) {
    fail(path, "only a rejected patch carries rejection reasons");
  }
  if ((patch.status === "COMMITTED") !== (patch.commit_sha !== null)) {
    fail(path, "a commit id is present exactly when the patch is committed");
  }
  if ((patch.status === "PROPOSED") !== (patch.decided_at === null)) {
    fail(path, "a decided patch has a decision time; a pending one does not");
  }
  return patch;
}

function parseRun(value: unknown, path: string): DreamRun {
  const d = r.object(value, path);
  const stages = r.array(d.stages, `${path}.stages`, DREAM_STAGES.length, 1).map((s, i) => {
    const st = r.object(s, `${path}.stages[${i}]`);
    return {
      stage: r.oneOf(st.stage, DREAM_STAGES, `${path}.stages[${i}].stage`),
      recorded_at: r.timestamp(st.recorded_at, `${path}.stages[${i}].recorded_at`),
      item_count: r.integer(st.item_count, `${path}.stages[${i}].item_count`, 0, 256),
      reason_codes: r.reasons(st.reason_codes, `${path}.stages[${i}].reason_codes`, 64),
    };
  });
  // Admission records the stages strictly in order.
  stages.forEach((s, i) => {
    if (s.stage !== DREAM_STAGES[i]) fail(`${path}.stages[${i}]`, "stages are out of order");
  });
  const run: DreamRun = {
    run_id: r.sha256(d.run_id, `${path}.run_id`),
    started_at: r.timestamp(d.started_at, `${path}.started_at`),
    stages,
    complete: r.bool(d.complete, `${path}.complete`),
    proposed: r.ids(d.proposed, `${path}.proposed`, 256, "mpt"),
  };
  if (run.complete !== (stages.length === DREAM_STAGES.length)) {
    fail(path, "a run is complete exactly when every stage is recorded");
  }
  return run;
}

function parseMemory(value: unknown, path: string): MemoryItem {
  const m = r.object(value, path);
  return {
    path: r.text(m.path, `${path}.path`),
    kind: r.oneOf(m.kind, MEMORY_KINDS, `${path}.kind`),
    title: r.text(m.title, `${path}.title`),
    body: r.text(m.body, `${path}.body`, 4000),
    subject: r.id(m.subject, `${path}.subject`),
    level: r.optional(m.level, (v) => level(v, `${path}.level`)),
    status: r.oneOf(m.status, LEARNING_STATUSES, `${path}.status`),
    scope: r.array(m.scope, `${path}.scope`, 16).map((t, i) => r.tag(t, `${path}.scope[${i}]`)),
    valid_from: r.optional(m.valid_from, (v) => r.timestamp(v, `${path}.valid_from`)),
    review_after: r.optional(m.review_after, (v) => r.timestamp(v, `${path}.review_after`)),
    sources: r.ids(m.sources, `${path}.sources`, 256, undefined, 1),
    counterevidence: r.ids(m.counterevidence, `${path}.counterevidence`, 256),
    revision: r.gitSha(m.revision, `${path}.revision`),
    written_by: r.optional(m.written_by, (v) => r.id(v, `${path}.written_by`, "mpt")),
    lineage: parseLineage(m.lineage, `${path}.lineage`),
  };
}

/** Validate an untrusted payload as a memory / Dream view, or throw MemoryValidationError. */
export function parseMemoryDreamView(value: unknown): MemoryDreamView {
  const v = r.object(value, "view");
  if (v.version !== VIEW_VERSION) fail("view.version", `expected ${VIEW_VERSION}`);
  const patches = r.array(v.patches, "view.patches", 4096).map((p, i) => parsePatch(p, `view.patches[${i}]`));
  const memories = r.array(v.memories, "view.memories", 4096).map((m, i) => parseMemory(m, `view.memories[${i}]`));
  const runs = r.array(v.dream_runs, "view.dream_runs", 4096).map((d, i) => parseRun(d, `view.dream_runs[${i}]`));
  const unreadable = r.array(v.unreadable, "view.unreadable", 4096).map((u, i) => {
    const o = r.object(u, `view.unreadable[${i}]`);
    return { path: r.text(o.path, `view.unreadable[${i}].path`), revision: r.gitSha(o.revision, `view.unreadable[${i}].revision`) };
  });

  // MemoryDreamView._references_resolve, plus the links the surface draws.
  const byId = new Map<string, Patch>();
  for (const [i, patch] of patches.entries()) {
    if (byId.has(patch.patch_id)) fail(`view.patches[${i}]`, "duplicate patch id");
    byId.set(patch.patch_id, patch);
  }
  for (const [i, memory] of memories.entries()) {
    if (memory.written_by === null) continue;
    const writer = byId.get(memory.written_by);
    if (!writer || writer.status !== "COMMITTED") {
      fail(`view.memories[${i}].written_by`, "names a patch that was not committed");
    }
    if (writer.commit_sha !== memory.revision) {
      fail(`view.memories[${i}].written_by`, "the patch did not write this revision");
    }
  }
  for (const [i, run] of runs.entries()) {
    for (const patchId of run.proposed) {
      const patch = byId.get(patchId);
      if (!patch) fail(`view.dream_runs[${i}].proposed`, `unknown patch ${patchId}`);
      if (patch.dream_run_id !== run.run_id) fail(`view.dream_runs[${i}].proposed`, `${patchId} belongs to another run`);
    }
  }
  return {
    version: VIEW_VERSION,
    ledger_head: r.sha256(v.ledger_head, "view.ledger_head"),
    memory_head: r.gitSha(v.memory_head, "view.memory_head"),
    memories,
    unreadable,
    dream_runs: runs,
    patches,
  };
}
