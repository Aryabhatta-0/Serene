import { wireReader } from "@/lib/wire";

// The `investigations` projection as the kernel writes it to
// serene.projection_state (serene/projections/investigations.py, Issue #35),
// arriving over the Realtime projection path (#33). Field names and enums
// mirror the kernel exactly.
//
// The surface never decides what Serene does next: `next_action` is the
// kernel's `serene.policies.investigation.next_action`, and `uncertainty` is
// the kernel's list of facts about what is not known. The parser fails closed
// on anything else, so a missing next action or a scored uncertainty can never
// be drawn.

export const PHASES = [
  "UNDERSTANDING",
  "RETRIEVING_CONTEXT",
  "FORMING_HYPOTHESES",
  "NEEDS_EVIDENCE",
  "ASKING_HUMAN",
  "RESEARCHING",
  "VERIFYING",
  "EVALUATING",
  "NEEDS_APPROVAL",
  "COMPLETE",
  "PARKED_UNRESOLVED",
] as const;
export type Phase = (typeof PHASES)[number];

export const STATUSES = [
  "OPEN",
  "GATHERING_EVIDENCE",
  "AWAITING_APPROVAL",
  "EXPERIMENTING",
  "PARKED_UNRESOLVED",
  "RESOLVED",
  "CLOSED",
] as const;
export type Status = (typeof STATUSES)[number];

export const NEXT_ACTIONS = [
  "UNDERSTAND_QUESTION",
  "RETRIEVE_CONTEXT",
  "FORM_HYPOTHESES",
  "CHOOSE_EVIDENCE",
  "WAIT_FOR_PARENT_ANSWER",
  "PROCESS_ANSWER",
  "RESEARCH",
  "VERIFY_EVIDENCE",
  "EVALUATE",
  "WAIT_FOR_APPROVAL",
  "NONE_COMPLETE",
  "NONE_PARKED",
] as const;
export type NextActionKind = (typeof NEXT_ACTIONS)[number];

export const UNCERTAINTY = [
  "NO_LIVE_EXPLANATION",
  "COMPETING_EXPLANATIONS",
  "NOTHING_TESTED",
  "PREDICTIONS_DISAGREE",
  "EVIDENCE_REQUESTED",
  "EVIDENCE_UNVERIFIED",
  "EVIDENCE_REJECTED",
  "ACQUISITION_EXHAUSTED",
  "PARKED_UNRESOLVED",
] as const;
export type Uncertainty = (typeof UNCERTAINTY)[number];

const LEVELS = ["RAW_EVIDENCE", "OBSERVATION", "PATTERN", "HYPOTHESIS", "TESTED_HYPOTHESIS", "CONTEXTUAL_LEARNING"] as const;
export type LevelName = (typeof LEVELS)[number];
const HYPOTHESIS_STATUSES = ["ACTIVE", "REFUTED", "SUPERSEDED"] as const;
const REQUEST_STATUSES = ["OPEN", "ANSWERED", "EXHAUSTED"] as const;
const MODES = ["ASK_PARENT", "BROWSE"] as const;
const VALUES = ["HIGH", "MEDIUM", "LOW"] as const;
const ANSWERS = ["YES", "NO"] as const;
const EVIDENCE_KINDS = ["PARENT_REPORT", "CAREGIVER_REPORT", "DOCUMENT", "BROWSER_CAPTURE"] as const;
const SOURCE_KINDS = ["TELEGRAM", "WEB_APP", "BROWSER", "EXTERNAL_DOCUMENT", "KERNEL", "EVAL_FIXTURE"] as const;
const VERIFICATION = ["UNVERIFIED", "VERIFIED", "REJECTED", "NOT_APPLICABLE"] as const;
const CHECKS = ["SOURCE_ALLOWED", "SUBJECT_MATCHES", "EFFECTIVE_DATE_VALID", "REQUESTED_FIELDS_PRESENT", "DIGEST_MATCHES", "CHANNEL_AUTHENTICATED", "PROVENANCE_VALID"] as const;
const HOST_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/;

export type Hypothesis = {
  hypothesis_id: string;
  statement: string;
  level: LevelName | null;
  status: (typeof HYPOTHESIS_STATUSES)[number];
  superseded_by: string | null;
  competing_hypothesis_ids: readonly string[];
  falsification_criteria: readonly string[];
  known_confounders: readonly string[];
  alternative_explanations: readonly string[];
};

export type EvidenceItem = {
  evidence_id: string;
  kind: (typeof EVIDENCE_KINDS)[number];
  source_kind: (typeof SOURCE_KINDS)[number];
  verification_status: (typeof VERIFICATION)[number];
  checks_passed: readonly (typeof CHECKS)[number][];
  rejection_reason_codes: readonly string[];
};

export type EvidenceRequest = {
  request_id: string;
  status: (typeof REQUEST_STATUSES)[number];
  requested_fields: readonly string[];
  acquisition_mode: (typeof MODES)[number] | null;
  question: string | null;
  subject: string | null;
  allowed_domains: readonly string[];
  information_value: (typeof VALUES)[number];
  rationale: string;
  predictions: readonly { hypothesis_id: string; expected: (typeof ANSWERS)[number]; live: boolean }[];
  failed_attempts: number;
  evidence: readonly EvidenceItem[];
};

export type NextAction = {
  kind: NextActionKind;
  phase: Phase;
  request_id: string | null;
  acquisition_mode: (typeof MODES)[number] | null;
  question: string | null;
  subject: string | null;
  allowed_domains: readonly string[];
  evidence_ids: readonly string[];
  experiment_ids: readonly string[];
  reason_codes: readonly string[];
};

export type Investigation = {
  investigation_id: string;
  question: string;
  status: Status;
  phase: Phase;
  opened_at: string;
  phase_reason_codes: readonly string[];
  hypotheses: readonly Hypothesis[];
  evidence_requests: readonly EvidenceRequest[];
  uncertainty: readonly Uncertainty[];
  next_action: NextAction;
};

export class InvestigationValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvestigationValidationError";
  }
}

function fail(path: string, problem: string): never {
  throw new InvestigationValidationError(`${path}: ${problem}`);
}
const r = wireReader(fail);

const texts = (value: unknown, path: string, max = 16) =>
  r.array(value, path, max).map((t, i) => r.text(t, `${path}[${i}]`));
const host = (value: unknown, path: string) => {
  const h = r.text(value, path, 253);
  if (!HOST_RE.test(h)) fail(path, "expected a host name");
  return h;
};

function parseNextAction(value: unknown, path: string): NextAction {
  const a = r.object(value, path);
  return {
    kind: r.oneOf(a.kind, NEXT_ACTIONS, `${path}.kind`),
    phase: r.oneOf(a.phase, PHASES, `${path}.phase`),
    request_id: r.optional(a.request_id, (v) => r.id(v, `${path}.request_id`, "erq")),
    acquisition_mode: r.optional(a.acquisition_mode, (v) => r.oneOf(v, MODES, `${path}.acquisition_mode`)),
    question: r.optional(a.question, (v) => r.text(v, `${path}.question`)),
    subject: r.optional(a.subject, (v) => r.tag(v, `${path}.subject`)),
    allowed_domains: r.array(a.allowed_domains, `${path}.allowed_domains`, 16).map((d, i) => host(d, `${path}.allowed_domains[${i}]`)),
    evidence_ids: r.ids(a.evidence_ids, `${path}.evidence_ids`, 256, "evd"),
    experiment_ids: r.ids(a.experiment_ids, `${path}.experiment_ids`, 64, "exp"),
    reason_codes: r.reasons(a.reason_codes, `${path}.reason_codes`, 64),
  };
}

function parseInvestigation(id: string, value: unknown, path: string): Investigation {
  const v = r.object(value, path);
  const investigation: Investigation = {
    investigation_id: r.id(id, `${path}.<key>`, "inv"),
    question: r.text(v.question, `${path}.question`),
    status: r.oneOf(v.status, STATUSES, `${path}.status`),
    phase: r.oneOf(v.phase, PHASES, `${path}.phase`),
    opened_at: r.timestamp(v.opened_at, `${path}.opened_at`),
    phase_reason_codes: r.reasons(v.phase_reason_codes, `${path}.phase_reason_codes`, 64),
    hypotheses: r.array(v.hypotheses, `${path}.hypotheses`, 64).map((h, i) => {
      const p = `${path}.hypotheses[${i}]`;
      const o = r.object(h, p);
      return {
        hypothesis_id: r.id(o.hypothesis_id, `${p}.hypothesis_id`, "hyp"),
        statement: r.text(o.statement, `${p}.statement`),
        level: r.optional(o.level, (l) => r.oneOf(l, LEVELS, `${p}.level`)),
        status: r.oneOf(o.status, HYPOTHESIS_STATUSES, `${p}.status`),
        superseded_by: r.optional(o.superseded_by, (s) => r.id(s, `${p}.superseded_by`, "hyp")),
        competing_hypothesis_ids: r.ids(o.competing_hypothesis_ids, `${p}.competing_hypothesis_ids`, 16, "hyp"),
        falsification_criteria: texts(o.falsification_criteria, `${p}.falsification_criteria`, 8),
        known_confounders: texts(o.known_confounders, `${p}.known_confounders`),
        alternative_explanations: texts(o.alternative_explanations, `${p}.alternative_explanations`),
      };
    }),
    evidence_requests: r.array(v.evidence_requests, `${path}.evidence_requests`, 64).map((q, i) => {
      const p = `${path}.evidence_requests[${i}]`;
      const o = r.object(q, p);
      return {
        request_id: r.id(o.request_id, `${p}.request_id`, "erq"),
        status: r.oneOf(o.status, REQUEST_STATUSES, `${p}.status`),
        requested_fields: r.array(o.requested_fields, `${p}.requested_fields`, 16, 1).map((t, j) => r.tag(t, `${p}.requested_fields[${j}]`)),
        acquisition_mode: r.optional(o.acquisition_mode, (m) => r.oneOf(m, MODES, `${p}.acquisition_mode`)),
        question: r.optional(o.question, (t) => r.text(t, `${p}.question`)),
        subject: r.optional(o.subject, (t) => r.tag(t, `${p}.subject`)),
        allowed_domains: r.array(o.allowed_domains, `${p}.allowed_domains`, 16).map((d, j) => host(d, `${p}.allowed_domains[${j}]`)),
        information_value: r.oneOf(o.information_value, VALUES, `${p}.information_value`),
        rationale: r.text(o.rationale, `${p}.rationale`),
        predictions: r.array(o.predictions, `${p}.predictions`, 16).map((x, j) => {
          const pp = r.object(x, `${p}.predictions[${j}]`);
          return {
            hypothesis_id: r.id(pp.hypothesis_id, `${p}.predictions[${j}].hypothesis_id`, "hyp"),
            expected: r.oneOf(pp.expected, ANSWERS, `${p}.predictions[${j}].expected`),
            live: r.bool(pp.live, `${p}.predictions[${j}].live`),
          };
        }),
        failed_attempts: r.integer(o.failed_attempts, `${p}.failed_attempts`, 0, 16),
        evidence: r.array(o.evidence, `${p}.evidence`, 64).map((e, j) => {
          const pe = `${p}.evidence[${j}]`;
          const ev = r.object(e, pe);
          return {
            evidence_id: r.id(ev.evidence_id, `${pe}.evidence_id`, "evd"),
            kind: r.oneOf(ev.kind, EVIDENCE_KINDS, `${pe}.kind`),
            source_kind: r.oneOf(ev.source_kind, SOURCE_KINDS, `${pe}.source_kind`),
            verification_status: r.oneOf(ev.verification_status, VERIFICATION, `${pe}.verification_status`),
            checks_passed: r.array(ev.checks_passed, `${pe}.checks_passed`, 8).map((c, k) => r.oneOf(c, CHECKS, `${pe}.checks_passed[${k}]`)),
            rejection_reason_codes: r.reasons(ev.rejection_reason_codes, `${pe}.rejection_reason_codes`, 64),
          };
        }),
      };
    }),
    uncertainty: r.array(v.uncertainty, `${path}.uncertainty`, UNCERTAINTY.length).map((u, i) =>
      r.oneOf(u, UNCERTAINTY, `${path}.uncertainty[${i}]`),
    ),
    next_action: parseNextAction(v.next_action, `${path}.next_action`),
  };
  // The kernel's own invariants for what is drawn.
  if (investigation.next_action.phase !== investigation.phase) fail(path, "the next action is for another phase");
  const live = investigation.hypotheses.filter((h) => h.status === "ACTIVE").length;
  if (live >= 2 && !investigation.uncertainty.includes("COMPETING_EXPLANATIONS")) {
    fail(path, "competing explanations must be stated as uncertainty");
  }
  if (live === 0 && !investigation.uncertainty.includes("NO_LIVE_EXPLANATION")) {
    fail(path, "having no live explanation must be stated as uncertainty");
  }
  if (new Set(investigation.uncertainty).size !== investigation.uncertainty.length) fail(path, "repeated uncertainty");
  return investigation;
}

/** Validate the `investigations` projection state, or throw InvestigationValidationError. */
export function parseInvestigations(value: unknown): Investigation[] {
  const map = r.object(value, "investigations");
  return Object.entries(map).map(([id, v]) => parseInvestigation(id, v, `investigations.${id}`));
}

/** The investigation the parent most needs to see: the newest still under way. */
export function current(investigations: readonly Investigation[]): Investigation | null {
  const open = investigations.filter((i) => i.phase !== "COMPLETE" && i.phase !== "PARKED_UNRESOLVED");
  const pool = open.length > 0 ? open : investigations;
  return [...pool].sort((a, b) => b.opened_at.localeCompare(a.opened_at))[0] ?? null;
}
