import type { Experiment, SafetyClass } from "./model";

// A parent's decision on one approval request, as the web app sends it to the
// kernel: `WebApprovalCommand` in serene/adapters/web/approvals.py.
//
// The command quotes back exactly what the parent was shown (the request's
// intervention digest and safety class). The kernel's channel and the ledger's
// admission decide whether it is recorded; this module only refuses to build
// a command that could never be valid, RED above all. Nothing here records,
// assumes or displays success: the surface shows the kernel's answer, and the
// experiment's state changes only when the projection does.

export type Decision = "APPROVE" | "DECLINE";

export type ApprovalCommand = {
  approval_request_id: string;
  decision: Decision;
  shown_intervention_digest: string;
  shown_safety_class: SafetyClass;
  request_id: string;
};

/** The kernel's answer (`WebDecisionResult`): the event it appended, or REFUSED with reasons. */
export type ApprovalResult =
  | { outcome: "APPROVAL_GRANTED" | "APPROVAL_REJECTED"; reason_codes: readonly string[] }
  | { outcome: "REFUSED"; reason_codes: readonly string[] };

/** Sends a command to the kernel and resolves with its answer. Supplied by the app's transport. */
export type ApprovalTransport = (command: ApprovalCommand) => Promise<unknown>;

export class NotDecidable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NotDecidable";
  }
}

const REQUEST_ID_RE = /^[A-Za-z0-9_-]{16,64}$/;
const REASON_RE = /^[A-Z][A-Z0-9_]{0,63}(:[A-Za-z0-9_]{1,64})?$/;

/** Whether the parent may still decide on this experiment's request at all. */
export function canDecide(experiment: Experiment): boolean {
  return experiment.phase === "AWAITING_APPROVAL" && experiment.approval?.decision_open === true;
}

/** Whether approving is possible. RED never is, whatever else the payload says. */
export function canApprove(experiment: Experiment): boolean {
  return (
    canDecide(experiment) &&
    experiment.safety_class !== "RED" &&
    experiment.approval?.safety_class !== "RED"
  );
}

export function buildApprovalCommand(experiment: Experiment, decision: Decision, requestId: string): ApprovalCommand {
  const approval = experiment.approval;
  if (!approval || !canDecide(experiment)) throw new NotDecidable("this request is not open for a decision");
  if (decision === "APPROVE" && !canApprove(experiment)) throw new NotDecidable("a RED experiment cannot be approved");
  if (!REQUEST_ID_RE.test(requestId)) throw new NotDecidable("the request id is malformed");
  return {
    approval_request_id: approval.approval_request_id,
    decision,
    shown_intervention_digest: approval.intervention_digest,
    shown_safety_class: approval.safety_class,
    request_id: requestId,
  };
}

/** Read the kernel's answer strictly. Anything unexpected is not treated as success. */
export function parseApprovalResult(value: unknown): ApprovalResult | null {
  if (typeof value !== "object" || value === null) return null;
  const { outcome, reason_codes } = value as { outcome?: unknown; reason_codes?: unknown };
  if (!Array.isArray(reason_codes) || !reason_codes.every((c) => typeof c === "string" && REASON_RE.test(c))) {
    return null;
  }
  if (outcome === "APPROVAL_GRANTED" || outcome === "APPROVAL_REJECTED") return { outcome, reason_codes };
  if (outcome === "REFUSED" && reason_codes.length > 0) return { outcome, reason_codes };
  return null;
}

export function newRequestId(): string {
  return `web-${crypto.randomUUID()}`;
}
