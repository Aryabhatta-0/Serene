"use client";

import { useId, useRef, useState } from "react";
import {
  buildApprovalCommand,
  canApprove,
  canDecide,
  newRequestId,
  parseApprovalResult,
  type ApprovalResult,
  type ApprovalTransport,
  type Decision,
} from "@/lib/experiments/approval";
import type { Experiment } from "@/lib/experiments/model";
import { Icon } from "@/components/system/Icon";
import { Reasons } from "@/components/system/Record";
import { SAFETY_LABELS, explainReason } from "@/lib/experiments/present";
import styles from "./Experiments.module.css";

type Step =
  | { kind: "idle" }
  | { kind: "confirming"; decision: Decision }
  | { kind: "sending"; decision: Decision }
  | { kind: "answered"; result: ApprovalResult }
  | { kind: "failed" };

type DecisionPanelProps = {
  experiment: Experiment;
  /** Sends the decision to the kernel. Absent until the web app is connected. */
  decide: ApprovalTransport | null;
};

// The parent's decision on one request (Issue #37). It builds the command the
// kernel expects and shows the kernel's answer, nothing else: no success is
// assumed, and the experiment's stage changes only when Serene's record does.
// RED is never approvable here: the button is not drawn, and the command
// builder refuses it as well.
export function DecisionPanel({ experiment, decide }: DecisionPanelProps) {
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const headingId = useId();
  const confirmRef = useRef<HTMLButtonElement>(null);
  const approval = experiment.approval;

  if (experiment.safety_class === "RED" || approval?.safety_class === "RED") {
    return (
      <div className={styles.decision} data-decision="not-approvable" role="note">
        <p className={styles.decisionTitle}>
          <Icon name="blocked" className={styles.decisionIcon} />
          This cannot be approved
        </p>
        <p>{SAFETY_LABELS.RED.description}</p>
        <p className={styles.decisionNote}>Serene fails closed: no button, link or message can start it.</p>
      </div>
    );
  }
  if (!approval || !canDecide(experiment)) {
    return (
      <div className={styles.decision} data-decision="closed" role="note">
        <p className={styles.decisionTitle}>
          <Icon name="ring" className={styles.decisionIcon} />
          No decision can be made now
        </p>
        <p>This request is no longer open, so nothing here can approve or decline it.</p>
      </div>
    );
  }
  if (decide === null) {
    return (
      <div className={styles.decision} data-decision="unconnected" role="note">
        <p className={styles.decisionTitle}>
          <Icon name="ring" className={styles.decisionIcon} />
          Deciding from this page is not connected yet
        </p>
        <p>Nothing on this page can approve or decline it. Nothing starts without your approval.</p>
      </div>
    );
  }

  const send = async (decision: Decision) => {
    setStep({ kind: "sending", decision });
    try {
      const command = buildApprovalCommand(experiment, decision, newRequestId());
      const result = parseApprovalResult(await decide(command));
      setStep(result ? { kind: "answered", result } : { kind: "failed" });
    } catch {
      setStep({ kind: "failed" });
    }
  };

  const approvable = canApprove(experiment);
  return (
    <section
      className={styles.decision}
      data-decision="open"
      data-safety={approval.safety_class}
      data-step={step.kind}
      aria-labelledby={headingId}
    >
      <h4 id={headingId} className={styles.decisionTitle}>
        <Icon name="hand" className={styles.decisionIcon} />
        Your decision
      </h4>
      {step.kind === "idle" ? (
        <>
          <p>
            You are deciding on exactly what is shown above. Its risk is rated “{SAFETY_LABELS[approval.safety_class].term}”.
            {approval.safety_class === "AMBER" ? " Take your time: an experiment that needs care cannot be approved straight away." : ""}
          </p>
          <ul className={styles.recap} aria-label="What you would be deciding">
            <li>
              <Icon name="undo" className={styles.recapIcon} />
              {experiment.intervention.reversible ? "Can be stopped and undone at any time" : "Could not be undone"}
            </li>
            <li>
              <Icon name="clock" className={styles.recapIcon} />
              Runs for {experiment.intervention.max_duration_days === 1 ? "one day" : `${experiment.intervention.max_duration_days} days`} at most
            </li>
            <li>
              <Icon name="eye" className={styles.recapIcon} />
              Judged by: {experiment.outcome_measure}
            </li>
          </ul>
          <div className={styles.actions}>
            {approvable ? (
              <button
                type="button"
                className="button"
                onClick={() => {
                  setStep({ kind: "confirming", decision: "APPROVE" });
                  requestAnimationFrame(() => confirmRef.current?.focus());
                }}
              >
                Approve
              </button>
            ) : null}
            <button
              type="button"
              className="button"
              onClick={() => {
                setStep({ kind: "confirming", decision: "DECLINE" });
                requestAnimationFrame(() => confirmRef.current?.focus());
              }}
            >
              Decline
            </button>
          </div>
        </>
      ) : null}

      {step.kind === "confirming" ? (
        <>
          <p>
            {step.decision === "APPROVE"
              ? "Approve this experiment? It can start once Serene records your approval, and you can stop it at any time."
              : "Decline this experiment? It will not run."}
          </p>
          <div className={styles.actions}>
            <button
              ref={confirmRef}
              type="button"
              className={step.decision === "APPROVE" ? "button button-solid" : "button"}
              onClick={() => send(step.decision)}
            >
              {step.decision === "APPROVE" ? "Yes, approve" : "Yes, decline"}
            </button>
            <button type="button" className="button" onClick={() => setStep({ kind: "idle" })}>
              Go back
            </button>
          </div>
        </>
      ) : null}

      <div role="status" aria-live="polite" className={styles.decisionStatus}>
        {step.kind === "sending" ? <p>Sending your decision to Serene…</p> : null}
        {step.kind === "answered" && step.result.outcome !== "REFUSED" ? (
          <p data-result="recorded">
            Serene recorded your {step.result.outcome === "APPROVAL_GRANTED" ? "approval" : "decision to decline"}. This page
            shows the new stage once Serene’s record updates.
          </p>
        ) : null}
        {step.kind === "answered" && step.result.outcome === "REFUSED" ? (
          <div data-result="refused">
            <p>Serene did not record this decision.</p>
            <Reasons codes={step.result.reason_codes} label="Why it was not recorded" explain={explainReason} tone="against" />
          </div>
        ) : null}
        {step.kind === "failed" ? (
          <p data-result="failed">
            Your decision could not be confirmed, so nothing is shown as decided. Check this page again before trying once more.
          </p>
        ) : null}
      </div>
      {step.kind === "answered" && step.result.outcome === "REFUSED" ? (
        <div className={styles.actions}>
          <button type="button" className="button" onClick={() => setStep({ kind: "idle" })}>
            Start again
          </button>
        </div>
      ) : null}
    </section>
  );
}
