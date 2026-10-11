import { LEVEL_NAMES } from "@/lib/causal-twin/provenance";
import type { Burden, Channel, ExperimentPhase, InterventionCategory, OutcomeResult, SafetyClass } from "./model";

// How the Experiments surface words what the kernel recorded. Every state is
// written out; codes from serene.policies (safety, experiments, approval,
// promotion) are explained where Serene knows them, and always shown.

export const PHASE_LABELS: Record<ExperimentPhase, { term: string; description: string }> = {
  PROPOSED: { term: "Proposed", description: "Suggested, and not yet checked for safety." },
  CLASSIFIED: { term: "Checked for safety", description: "Checked for safety. It has not been put to you yet." },
  BLOCKED: { term: "Blocked", description: "Serene will not run this. It cannot be approved." },
  AWAITING_APPROVAL: { term: "Waiting for your decision", description: "Nothing starts unless you approve it." },
  APPROVED: { term: "Approved", description: "You approved it. It has not started yet." },
  WAITING_FOR_OUTCOME: { term: "Running", description: "Under way. Serene is waiting to hear how it went." },
  OUTCOME_OVERDUE: {
    term: "Outcome overdue",
    description: "Its time is up and no outcome has been reported. It will be stopped, not guessed at.",
  },
  COMPLETED: { term: "Finished", description: "Finished, with the outcomes below." },
  ABANDONED: { term: "Stopped", description: "Stopped before it finished." },
  PARKED_UNRESOLVED: { term: "Expired", description: "No decision was made in time, so it never started." },
};

export const SAFETY_LABELS: Record<SafetyClass, { term: string; description: string }> = {
  GREEN: { term: "Low", description: "Small, low-effort and easy to undo." },
  AMBER: {
    term: "Needs care",
    description: "Touches something that matters more, such as sleep or meals. Take time to decide.",
  },
  RED: { term: "Not allowed", description: "Serene never runs experiments of this kind. It cannot be approved." },
};

export const CATEGORY_LABELS: Record<InterventionCategory, string> = {
  ROUTINE_TIMING: "Routine timing",
  ENVIRONMENT: "Surroundings",
  TRANSITION_SUPPORT: "Help with a change of activity",
  COMMUNICATION: "How things are said",
  PLAY_ACTIVITY: "Play",
  CAREGIVER_COORDINATION: "Coordinating with caregivers",
  SLEEP_SCHEDULE: "Sleep",
  MEAL_TIMING: "Meals",
  SCREEN_TIME: "Screen time",
  MEDICATION: "Medication",
  SUPPLEMENT: "Supplements",
  ALLERGEN_EXPOSURE: "Allergens",
  SYMPTOM_TREATMENT: "Treating symptoms",
};

export const BURDEN_LABELS: Record<Burden, string> = { LOW: "Low", MEDIUM: "Medium", HIGH: "High" };

export const RESULT_LABELS: Record<OutcomeResult, string> = {
  SUPPORTS: "Supports the explanation",
  CONTRADICTS: "Contradicts the explanation",
  INCONCLUSIVE: "Inconclusive",
};

export const CHANNEL_LABELS: Record<Channel, string> = {
  TELEGRAM: "in Telegram",
  WEB_APP: "in the web app",
  BROWSER: "from a web page",
  EXTERNAL_DOCUMENT: "from a document",
  KERNEL: "by Serene",
  EVAL_FIXTURE: "in a test",
};

const EXACT: Record<string, string> = {
  LOW_RISK_REVERSIBLE: "A small change that is easy to undo.",
  RED_FAIL_CLOSED: "Anything judged unsafe is refused outright.",
  FORBIDDEN_TERM: "It mentions something Serene never experiments with.",
  IRREVERSIBLE: "It could not be undone.",
  NOT_REVERSIBLE: "It could not be undone.",
  EXTENDED_DURATION: "It would run for longer than a short trial.",
  EXCEEDS_MAX_DURATION: "It would run for longer than Serene allows.",
  MISSING_COMPARISON: "It does not say what it would be compared with.",
  MISSING_INTERVENTION: "It does not say what would change.",
  MISSING_OUTCOME_MEASURE: "It does not say how the result would be judged.",
  INDISTINCT_SPECIFICATION: "What would change, and how it would be judged, are not distinct enough.",
  SCOPE_TOO_BROAD: "It would apply to more situations than were observed.",
  SCOPE_EXCEEDS_HYPOTHESIS: "It would apply to more situations than the explanation covers.",
  HYPOTHESIS_INACTIVE: "The explanation it tests is no longer held.",
  INVESTIGATION_CLOSED: "The question it belongs to has been closed.",
  ALLOWED: "Every condition for promotion was met.",
  NO_SUPPORTING_OUTCOME: "No outcome supported the explanation.",
  CONTRADICTING_OUTCOME: "An outcome contradicted the explanation.",
  NO_APPROVED_COMPLETED_EXPERIMENT: "No approved experiment has finished.",
  NO_ALTERNATIVES_CONSIDERED: "Other explanations were not considered.",
  NO_CONFOUNDERS_CONSIDERED: "Things that could confuse the result were not considered.",
  SINGLE_OCCASION: "It rests on a single occasion.",
  INSUFFICIENT_OBSERVATIONS: "There are not enough observations.",
  // Refusals of a decision (serene.policies.approval)
  RED_CANNOT_BE_APPROVED: "A RED experiment can never be approved.",
  APPROVAL_EXPIRED: "The request expired before the decision arrived.",
  AMBER_DELIBERATION_TOO_SHORT: "An experiment that needs care cannot be approved this soon after it was asked. Please try again later.",
  INTERVENTION_DIGEST_MISMATCH: "The experiment changed after you were shown it. Look at it again before deciding.",
  SAFETY_CLASS_NOT_ACKNOWLEDGED: "The risk you were shown does not match the record. Look at it again before deciding.",
  SAFETY_CLASS_CHANGED_SINCE_REQUEST: "Its risk was reassessed after you were asked.",
  APPROVER_NOT_PARENT: "Only a parent can decide.",
  APPROVER_MISMATCH: "This request was put to another parent.",
  UNAUTHENTICATED_CHANNEL: "The decision did not come over a signed-in channel.",
  CHANNEL_MISMATCH: "The decision did not come over a signed-in channel.",
  RECEIPT_REPLAYED: "This decision was already sent once.",
  RECEIPT_IN_FUTURE: "The decision's time could not be trusted.",
  RECEIPT_PREDATES_REQUEST: "The decision's time could not be trusted.",
  UNKNOWN_APPROVAL_REQUEST: "Serene has no such request.",
};

const PREFIXED: Record<string, string> = {
  FORBIDDEN_CATEGORY: "Serene never experiments with this kind of change.",
  UNCLASSIFIABLE: "Its kind of change could not be classified, so it is refused.",
  ESCALATED_CATEGORY: "This kind of change always needs extra care.",
  BURDEN: "It asks more of your family than a small trial should.",
  APPROVAL_NOT_OPEN: "This request is no longer open for a decision.",
  EXPERIMENT_NOT_AWAITING_APPROVAL: "This experiment is no longer waiting for a decision.",
  EXPERIMENT_REQUIREMENTS_UNMET: "It no longer meets the conditions for running.",
  UNRESOLVED_COMPETITOR: "A competing explanation has not been ruled out.",
  UNVERIFIED_EVIDENCE: "Some of the evidence has not been verified.",
  OUTCOME_OMITTED: "A reported outcome was left out.",
  LEVEL_MISMATCH: "The explanation is not at the level this step needs.",
};

export type ReasonText = { code: string; text: string; known: boolean };

/** A recorded reason in plain words, keeping its code. */
export function explainReason(code: string): ReasonText {
  if (code in EXACT) return { code, text: EXACT[code], known: true };
  const head = code.split(":", 1)[0];
  if (head in PREFIXED) return { code, text: PREFIXED[head], known: true };
  return { code, text: "Recorded reason (Serene has no plain description for this code yet).", known: false };
}

export function promotionText(granted: boolean, to: keyof typeof LEVEL_NAMES): string {
  const name = LEVEL_NAMES[to].toLowerCase();
  return granted
    ? `Promoted: the explanation is now held as a ${name}.`
    : `Not promoted: the explanation stays where it was, not a ${name}.`;
}

/** How the surface groups experiments, so what needs the parent comes first. */
export const GROUPS: readonly { title: string; phases: readonly ExperimentPhase[]; empty: string }[] = [
  { title: "Waiting for your decision", phases: ["AWAITING_APPROVAL"], empty: "Nothing is waiting for you." },
  {
    title: "Approved and running",
    phases: ["APPROVED", "WAITING_FOR_OUTCOME", "OUTCOME_OVERDUE"],
    empty: "Nothing is running.",
  },
  {
    title: "Not put to you",
    phases: ["PROPOSED", "CLASSIFIED", "BLOCKED"],
    empty: "Nothing else has been proposed.",
  },
  { title: "Finished", phases: ["COMPLETED", "ABANDONED", "PARKED_UNRESOLVED"], empty: "Nothing has finished yet." },
];
