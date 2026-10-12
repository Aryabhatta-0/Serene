import type { EvidenceItem, EvidenceRequest, Hypothesis, LevelName, NextAction, NextActionKind, Phase, Uncertainty } from "./model";

// How the Today and Investigations surfaces word the kernel's projection.
// What Serene does next is never decided here: the kind comes from
// `serene.policies.investigation.next_action`, and the specifics (which
// question, which source, which evidence) come from the records it read.
// This file only puts them into words.

export const PHASE_LABELS: Record<Phase, string> = {
  UNDERSTANDING: "Understanding the question",
  RETRIEVING_CONTEXT: "Gathering what is already known",
  FORMING_HYPOTHESES: "Forming explanations",
  NEEDS_EVIDENCE: "Choosing what evidence would help",
  ASKING_HUMAN: "Asking you",
  RESEARCHING: "Looking it up",
  VERIFYING: "Checking the evidence",
  EVALUATING: "Weighing the evidence",
  NEEDS_APPROVAL: "Waiting for your approval",
  COMPLETE: "Finished",
  PARKED_UNRESOLVED: "Paused without an answer",
};

export const LEVEL_LABELS: Record<LevelName, string> = {
  RAW_EVIDENCE: "Raw evidence",
  OBSERVATION: "Observation",
  PATTERN: "Pattern",
  HYPOTHESIS: "Possible explanation, not tested",
  TESTED_HYPOTHESIS: "Tested in your family",
  CONTEXTUAL_LEARNING: "Learned, in these situations",
};

export const HYPOTHESIS_STATUS_LABELS: Record<Hypothesis["status"], string> = {
  ACTIVE: "Still being weighed",
  REFUTED: "Ruled out",
  SUPERSEDED: "Replaced by a better-formed explanation",
};

export const UNCERTAINTY_TEXT: Record<Uncertainty, string> = {
  NO_LIVE_EXPLANATION: "No explanation is still standing.",
  COMPETING_EXPLANATIONS: "More than one explanation still fits. Serene has not picked one.",
  NOTHING_TESTED: "None of the explanations has been tested in your family.",
  PREDICTIONS_DISAGREE: "The explanations predict different answers to the open question, so the answer matters.",
  EVIDENCE_REQUESTED: "Evidence has been asked for and has not arrived yet.",
  EVIDENCE_UNVERIFIED: "Some evidence has arrived but has not been checked yet.",
  EVIDENCE_REJECTED: "Some evidence failed its checks and is not used.",
  ACQUISITION_EXHAUSTED: "Serene tried to get some evidence and could not.",
  PARKED_UNRESOLVED: "The investigation stopped before reaching an answer.",
};

export const REQUEST_STATUS_LABELS: Record<EvidenceRequest["status"], string> = {
  OPEN: "Still missing",
  ANSWERED: "Received",
  EXHAUSTED: "Could not be obtained",
};

export const VALUE_LABELS: Record<EvidenceRequest["information_value"], string> = {
  HIGH: "High: the explanations predict different answers",
  MEDIUM: "Medium: it bears on one explanation",
  LOW: "Low",
};

export const VERIFICATION_LABELS: Record<EvidenceItem["verification_status"], string> = {
  UNVERIFIED: "Not checked yet",
  VERIFIED: "Checked and accepted",
  REJECTED: "Failed its checks",
  NOT_APPLICABLE: "No check applies",
};

export const EVIDENCE_KIND_LABELS: Record<EvidenceItem["kind"], string> = {
  PARENT_REPORT: "Your answer",
  CAREGIVER_REPORT: "A caregiver’s report",
  DOCUMENT: "A document",
  BROWSER_CAPTURE: "A web page",
};

export const CHANNEL_LABELS: Record<EvidenceItem["source_kind"], string> = {
  TELEGRAM: "over Telegram",
  WEB_APP: "in the web app",
  BROWSER: "from the web",
  EXTERNAL_DOCUMENT: "from a document",
  KERNEL: "from Serene",
  EVAL_FIXTURE: "from a test",
};

export const CHECK_LABELS: Record<EvidenceItem["checks_passed"][number], string> = {
  SOURCE_ALLOWED: "From an allowed source",
  SUBJECT_MATCHES: "About the right thing",
  EFFECTIVE_DATE_VALID: "Current",
  REQUESTED_FIELDS_PRESENT: "Answers what was asked",
  DIGEST_MATCHES: "Unaltered",
  CHANNEL_AUTHENTICATED: "Came over a signed-in channel",
  PROVENANCE_VALID: "Its origin checks out",
};

/** Where the selected evidence comes from, in words. */
export function sourceText(mode: EvidenceRequest["acquisition_mode"], domains: readonly string[], subject: string | null): string {
  if (mode === "ASK_PARENT") return "Asking you one yes-or-no question";
  if (mode === "BROWSE") {
    const where = domains.length > 0 ? ` on ${domains.join(", ")}` : "";
    const what = subject ? ` about ${subject.replace(/_+/g, " ")}` : "";
    return `Looking it up${what}${where}`;
  }
  return "No source recorded";
}

/** The kernel's next action, in words. The kind and its details are the kernel's. */
export function nextActionText(action: NextAction): { title: string; detail: string | null } {
  const titles: Record<NextActionKind, string> = {
    UNDERSTAND_QUESTION: "Serene will make sure it understands the question.",
    RETRIEVE_CONTEXT: "Serene will gather what it already knows.",
    FORM_HYPOTHESES: "Serene will form competing explanations.",
    CHOOSE_EVIDENCE: "Serene will choose the single most useful piece of evidence, if any is needed.",
    WAIT_FOR_PARENT_ANSWER: "Serene is waiting for your answer.",
    PROCESS_ANSWER: "Serene has your answer and will check it.",
    RESEARCH: "Serene will look this up.",
    VERIFY_EVIDENCE: "Serene will check the evidence before using it.",
    EVALUATE: "Serene will weigh the evidence against each explanation.",
    WAIT_FOR_APPROVAL: "Serene is waiting for your decision on an experiment.",
    NONE_COMPLETE: "Nothing more: this investigation is finished.",
    NONE_PARKED: "Nothing more for now: this investigation is paused.",
  };
  let detail: string | null = null;
  if (action.question) detail = `“${action.question}”`;
  else if (action.kind === "RESEARCH") detail = sourceText(action.acquisition_mode, action.allowed_domains, action.subject);
  else if (action.kind === "VERIFY_EVIDENCE") {
    detail = action.evidence_ids.length === 0 ? "Nothing is waiting to be checked." : null;
  } else if (action.kind === "WAIT_FOR_APPROVAL") {
    detail = action.experiment_ids.length === 1 ? "One experiment is waiting." : `${action.experiment_ids.length} experiments are waiting.`;
  }
  return { title: titles[action.kind], detail };
}

const REASONS: Record<string, string> = {
  PARENT_NO_RESPONSE: "No answer came in time.",
  EVIDENCE_BUDGET_EXHAUSTED: "Serene reached its limit on how much evidence to gather.",
  PLANNER_UNAVAILABLE: "Serene could not plan its next step.",
  NO_LIVE_HYPOTHESIS: "No explanation was left standing.",
  INSUFFICIENT_COMPETING_HYPOTHESES: "There were not two explanations to compare.",
  NO_OBSERVATIONS: "There was nothing observed to go on.",
  NO_EVIDENCE_SERVICE: "Serene could not reach a source of evidence.",
  APPROVAL_TIMED_OUT: "No decision on the experiment came in time.",
  EVIDENCE_SUFFICIENT: "The evidence was enough to stop asking.",
  COMPETING_HYPOTHESES_RETAINED: "More than one explanation is still kept; none was declared the answer.",
  EVIDENCE_DECIDED: "Every piece of evidence was checked.",
  ANSWER_RECEIVED: "Your answer arrived.",
  QUESTION_SELECTED: "One question was chosen to ask you.",
};

/** A recorded reason in words, keeping its code. */
export function explainReason(code: string): { code: string; text: string; known: boolean } {
  const head = code.split(":", 1)[0];
  if (head in REASONS) return { code, text: REASONS[head], known: true };
  return { code, text: "Recorded reason (Serene has no plain description for this code yet).", known: false };
}

/** The rung a hypothesis's level names, for the epistemic ladder. */
export const LEVEL_NUMBERS: Record<LevelName, 0 | 1 | 2 | 3 | 4 | 5> = {
  RAW_EVIDENCE: 0,
  OBSERVATION: 1,
  PATTERN: 2,
  HYPOTHESIS: 3,
  TESTED_HYPOTHESIS: 4,
  CONTEXTUAL_LEARNING: 5,
};

export type InvestigationStage = {
  key: string;
  label: string;
  state: "done" | "current" | "upcoming" | "stopped";
};

const STAGES: readonly { key: string; label: string; phases: readonly Phase[] }[] = [
  { key: "understand", label: "Understand", phases: ["UNDERSTANDING", "RETRIEVING_CONTEXT"] },
  { key: "explain", label: "Form explanations", phases: ["FORMING_HYPOTHESES"] },
  { key: "gather", label: "Gather evidence", phases: ["NEEDS_EVIDENCE", "ASKING_HUMAN", "RESEARCHING"] },
  { key: "verify", label: "Check evidence", phases: ["VERIFYING"] },
  { key: "weigh", label: "Weigh and decide", phases: ["EVALUATING", "NEEDS_APPROVAL"] },
  { key: "end", label: "Finished", phases: ["COMPLETE"] },
];

/**
 * Where an investigation stands, as stages of the kernel's own phases. Only
 * the phase moves the track. A paused investigation does not record where it
 * paused, so a stage before it is marked passed only when the record shows it
 * (explanations formed, evidence asked for, evidence received).
 */
export function investigationStages(inv: {
  phase: Phase;
  hypotheses: readonly unknown[];
  evidence_requests: readonly { evidence: readonly unknown[] }[];
}): InvestigationStage[] {
  if (inv.phase === "PARKED_UNRESOLVED") {
    const reached: Record<string, boolean> = {
      understand: true,
      explain: inv.hypotheses.length > 0,
      gather: inv.evidence_requests.length > 0,
      verify: inv.evidence_requests.some((r) => r.evidence.length > 0),
      weigh: false,
    };
    return [
      ...STAGES.slice(0, -1).map((s) => ({ key: s.key, label: s.label, state: reached[s.key] ? ("done" as const) : ("upcoming" as const) })),
      { key: "end", label: "Paused without an answer", state: "stopped" },
    ];
  }
  const at = STAGES.findIndex((s) => s.phases.includes(inv.phase));
  return STAGES.map((s, i) => ({
    key: s.key,
    label: s.label,
    state: i < at ? "done" : i === at ? "current" : "upcoming",
  }));
}
