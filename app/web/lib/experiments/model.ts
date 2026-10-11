import type { ActorKind, EpistemicLevel } from "@/lib/causal-twin/model";
import { wireReader } from "@/lib/wire";

// Experiments and their approvals as the kernel serializes them:
// `ExperimentsView.model_dump(mode="json")` from serene/experiments/view.py
// (Issue #37). Field names and enums mirror the Pydantic models exactly.
//
// The view decides nothing. `parseExperimentsView` re-checks the kernel's own
// invariants and rejects anything else; above all, a RED experiment can never
// arrive with a decision open, so it can never be drawn as approvable.

export const VIEW_VERSION = "experiments-view/1";

export type SafetyClass = "GREEN" | "AMBER" | "RED";
export type ExperimentPhase =
  | "PROPOSED"
  | "CLASSIFIED"
  | "BLOCKED"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "WAITING_FOR_OUTCOME"
  | "OUTCOME_OVERDUE"
  | "COMPLETED"
  | "ABANDONED"
  | "PARKED_UNRESOLVED";
export type ApprovalState = "PENDING" | "NUDGED" | "GRANTED" | "REJECTED" | "PARKED_UNRESOLVED";
export type OutcomeResult = "SUPPORTS" | "CONTRADICTS" | "INCONCLUSIVE";
export type Burden = "LOW" | "MEDIUM" | "HIGH";
export type InterventionCategory =
  | "ROUTINE_TIMING"
  | "ENVIRONMENT"
  | "TRANSITION_SUPPORT"
  | "COMMUNICATION"
  | "PLAY_ACTIVITY"
  | "CAREGIVER_COORDINATION"
  | "SLEEP_SCHEDULE"
  | "MEAL_TIMING"
  | "SCREEN_TIME"
  | "MEDICATION"
  | "SUPPLEMENT"
  | "ALLERGEN_EXPOSURE"
  | "SYMPTOM_TREATMENT";
export type Channel = "TELEGRAM" | "WEB_APP" | "BROWSER" | "EXTERNAL_DOCUMENT" | "KERNEL" | "EVAL_FIXTURE";

export type Intervention = {
  category: InterventionCategory;
  description: string;
  reversible: boolean;
  max_duration_days: number;
  burden: Burden;
};

export type Approval = {
  approval_request_id: string;
  state: ApprovalState;
  safety_class: SafetyClass;
  intervention_digest: string;
  requested_at: string | null;
  expires_at: string;
  nudges: number;
  decided_at: string | null;
  decided_via: Channel | null;
  decision_open: boolean;
};

export type Outcome = {
  outcome_id: string;
  result: OutcomeResult;
  summary: string;
  reported_at: string;
  reported_by: ActorKind;
};

export type Promotion = {
  granted: boolean;
  from_level: EpistemicLevel;
  to_level: EpistemicLevel;
  reason_codes: readonly string[];
  recorded_at: string | null;
};

export type Experiment = {
  experiment_id: string;
  hypothesis_id: string;
  hypothesis_statement: string | null;
  investigation_id: string;
  intervention: Intervention;
  comparison: string;
  outcome_measure: string;
  contexts: readonly string[];
  safety_class: SafetyClass | null;
  classification_reasons: readonly string[];
  phase: ExperimentPhase;
  proposed_at: string | null;
  started_at: string | null;
  outcome_due_at: string | null;
  ended_at: string | null;
  blocked_reasons: readonly string[];
  abandoned_reasons: readonly string[];
  outcome_timed_out: boolean;
  approval: Approval | null;
  outcomes: readonly Outcome[];
  promotion: Promotion | null;
};

export type ExperimentsView = {
  version: typeof VIEW_VERSION;
  ledger_head: string;
  as_of: string;
  experiments: readonly Experiment[];
};

export class ExperimentsValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExperimentsValidationError";
  }
}

function fail(path: string, problem: string): never {
  throw new ExperimentsValidationError(`${path}: ${problem}`);
}
const r = wireReader(fail);

export const PHASES: readonly ExperimentPhase[] = [
  "PROPOSED",
  "CLASSIFIED",
  "BLOCKED",
  "AWAITING_APPROVAL",
  "APPROVED",
  "WAITING_FOR_OUTCOME",
  "OUTCOME_OVERDUE",
  "COMPLETED",
  "ABANDONED",
  "PARKED_UNRESOLVED",
];
const SAFETY: readonly SafetyClass[] = ["GREEN", "AMBER", "RED"];
const APPROVAL_STATES: readonly ApprovalState[] = ["PENDING", "NUDGED", "GRANTED", "REJECTED", "PARKED_UNRESOLVED"];
const RESULTS: readonly OutcomeResult[] = ["SUPPORTS", "CONTRADICTS", "INCONCLUSIVE"];
const BURDENS: readonly Burden[] = ["LOW", "MEDIUM", "HIGH"];
const CATEGORIES: readonly InterventionCategory[] = [
  "ROUTINE_TIMING",
  "ENVIRONMENT",
  "TRANSITION_SUPPORT",
  "COMMUNICATION",
  "PLAY_ACTIVITY",
  "CAREGIVER_COORDINATION",
  "SLEEP_SCHEDULE",
  "MEAL_TIMING",
  "SCREEN_TIME",
  "MEDICATION",
  "SUPPLEMENT",
  "ALLERGEN_EXPOSURE",
  "SYMPTOM_TREATMENT",
];
const CHANNELS: readonly Channel[] = ["TELEGRAM", "WEB_APP", "BROWSER", "EXTERNAL_DOCUMENT", "KERNEL", "EVAL_FIXTURE"];
const ACTOR_KINDS: readonly ActorKind[] = [
  "PARENT",
  "CAREGIVER",
  "AGENT",
  "POLICY",
  "VERIFIER",
  "SYSTEM",
  "MEMORY_COMMITTER",
];
const OPEN_STATES: ReadonlySet<ApprovalState> = new Set(["PENDING", "NUDGED"]);

function time(value: unknown, path: string): string | null {
  return r.optional(value, (v) => r.timestamp(v, path));
}

function level(value: unknown, path: string): EpistemicLevel {
  return r.integer(value, path, 0, 5) as EpistemicLevel;
}

function parseApproval(value: unknown, path: string): Approval {
  const a = r.object(value, path);
  const approval: Approval = {
    approval_request_id: r.id(a.approval_request_id, `${path}.approval_request_id`, "apr"),
    state: r.oneOf(a.state, APPROVAL_STATES, `${path}.state`),
    safety_class: r.oneOf(a.safety_class, SAFETY, `${path}.safety_class`),
    intervention_digest: r.sha256(a.intervention_digest, `${path}.intervention_digest`),
    requested_at: time(a.requested_at, `${path}.requested_at`),
    expires_at: r.timestamp(a.expires_at, `${path}.expires_at`),
    nudges: r.integer(a.nudges, `${path}.nudges`, 0, 1000),
    decided_at: time(a.decided_at, `${path}.decided_at`),
    decided_via: r.optional(a.decided_via, (v) => r.oneOf(v, CHANNELS, `${path}.decided_via`)),
    decision_open: r.bool(a.decision_open, `${path}.decision_open`),
  };
  // ApprovalView._red_is_never_open, and an open decision is an open request.
  if (approval.safety_class === "RED" && approval.decision_open) fail(path, "a RED request can never be open");
  if (approval.decision_open && !OPEN_STATES.has(approval.state)) fail(path, "a closed request cannot be open");
  return approval;
}

function parseExperiment(value: unknown, path: string): Experiment {
  const e = r.object(value, path);
  const iv = r.object(e.intervention, `${path}.intervention`);
  const experiment: Experiment = {
    experiment_id: r.id(e.experiment_id, `${path}.experiment_id`, "exp"),
    hypothesis_id: r.id(e.hypothesis_id, `${path}.hypothesis_id`, "hyp"),
    hypothesis_statement: r.optional(e.hypothesis_statement, (v) => r.text(v, `${path}.hypothesis_statement`)),
    investigation_id: r.id(e.investigation_id, `${path}.investigation_id`, "inv"),
    intervention: {
      category: r.oneOf(iv.category, CATEGORIES, `${path}.intervention.category`),
      description: r.text(iv.description, `${path}.intervention.description`),
      reversible: r.bool(iv.reversible, `${path}.intervention.reversible`),
      max_duration_days: r.integer(iv.max_duration_days, `${path}.intervention.max_duration_days`, 1, 365),
      burden: r.oneOf(iv.burden, BURDENS, `${path}.intervention.burden`),
    },
    comparison: r.text(e.comparison, `${path}.comparison`),
    outcome_measure: r.text(e.outcome_measure, `${path}.outcome_measure`),
    contexts: r.array(e.contexts, `${path}.contexts`, 16).map((t, i) => r.tag(t, `${path}.contexts[${i}]`)),
    safety_class: r.optional(e.safety_class, (v) => r.oneOf(v, SAFETY, `${path}.safety_class`)),
    classification_reasons: r.reasons(e.classification_reasons, `${path}.classification_reasons`, 64),
    phase: r.oneOf(e.phase, PHASES, `${path}.phase`),
    proposed_at: time(e.proposed_at, `${path}.proposed_at`),
    started_at: time(e.started_at, `${path}.started_at`),
    outcome_due_at: time(e.outcome_due_at, `${path}.outcome_due_at`),
    ended_at: time(e.ended_at, `${path}.ended_at`),
    blocked_reasons: r.reasons(e.blocked_reasons, `${path}.blocked_reasons`, 64),
    abandoned_reasons: r.reasons(e.abandoned_reasons, `${path}.abandoned_reasons`, 64),
    outcome_timed_out: r.bool(e.outcome_timed_out, `${path}.outcome_timed_out`),
    approval: r.optional(e.approval, (v) => parseApproval(v, `${path}.approval`)),
    outcomes: r.array(e.outcomes, `${path}.outcomes`, 64).map((o, i) => {
      const out = r.object(o, `${path}.outcomes[${i}]`);
      return {
        outcome_id: r.id(out.outcome_id, `${path}.outcomes[${i}].outcome_id`, "out"),
        result: r.oneOf(out.result, RESULTS, `${path}.outcomes[${i}].result`),
        summary: r.text(out.summary, `${path}.outcomes[${i}].summary`),
        reported_at: r.timestamp(out.reported_at, `${path}.outcomes[${i}].reported_at`),
        reported_by: r.oneOf(out.reported_by, ACTOR_KINDS, `${path}.outcomes[${i}].reported_by`),
      };
    }),
    promotion: r.optional(e.promotion, (v) => {
      const p = r.object(v, `${path}.promotion`);
      return {
        granted: r.bool(p.granted, `${path}.promotion.granted`),
        from_level: level(p.from_level, `${path}.promotion.from_level`),
        to_level: level(p.to_level, `${path}.promotion.to_level`),
        reason_codes: r.reasons(p.reason_codes, `${path}.promotion.reason_codes`, 64),
        recorded_at: time(p.recorded_at, `${path}.promotion.recorded_at`),
      };
    }),
  };
  // ExperimentView._state_is_explained
  if (experiment.phase === "BLOCKED" && experiment.blocked_reasons.length === 0) {
    fail(path, "a blocked experiment carries the reasons it was blocked");
  }
  if (experiment.phase === "COMPLETED" && experiment.outcomes.length === 0) {
    fail(path, "a completed experiment carries its outcomes");
  }
  if (experiment.safety_class === "RED" && experiment.phase !== "BLOCKED" && experiment.phase !== "CLASSIFIED") {
    fail(path, "a RED experiment can only be classified or blocked");
  }
  if (experiment.approval?.decision_open && experiment.phase !== "AWAITING_APPROVAL") {
    fail(path, "only an experiment awaiting approval has an open decision");
  }
  if (experiment.approval && experiment.safety_class !== experiment.approval.safety_class) {
    fail(path, "the request's safety class must be the experiment's");
  }
  return experiment;
}

/** Validate an untrusted payload as the experiments view, or throw ExperimentsValidationError. */
export function parseExperimentsView(value: unknown): ExperimentsView {
  const v = r.object(value, "view");
  if (v.version !== VIEW_VERSION) fail("view.version", `expected ${VIEW_VERSION}`);
  const experiments = r
    .array(v.experiments, "view.experiments", 4096)
    .map((e, i) => parseExperiment(e, `view.experiments[${i}]`));
  const seen = new Set<string>();
  for (const [i, e] of experiments.entries()) {
    if (seen.has(e.experiment_id)) fail(`view.experiments[${i}]`, "duplicate experiment id");
    seen.add(e.experiment_id);
  }
  return {
    version: VIEW_VERSION,
    ledger_head: r.sha256(v.ledger_head, "view.ledger_head"),
    as_of: r.timestamp(v.as_of, "view.as_of"),
    experiments,
  };
}
