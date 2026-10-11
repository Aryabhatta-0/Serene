"use client";

import { useId, type ReactNode } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { LineMark, type Certainty } from "@/components/notation/LineMark";
import { variableLabel } from "@/lib/causal-twin/categories";
import { ACTOR_LABELS, formatDate } from "@/lib/causal-twin/provenance";
import type { ApprovalTransport } from "@/lib/experiments/approval";
import type { Experiment, ExperimentPhase, ExperimentsView as View } from "@/lib/experiments/model";
import {
  BURDEN_LABELS,
  CATEGORY_LABELS,
  CHANNEL_LABELS,
  GROUPS,
  PHASE_LABELS,
  RESULT_LABELS,
  SAFETY_LABELS,
  explainReason,
  promotionText,
} from "@/lib/experiments/present";
import type { ExperimentsSource } from "@/lib/experiments/source";
import { DecisionPanel } from "./DecisionPanel";
import styles from "./Experiments.module.css";

type ExperimentsViewProps = {
  source: ExperimentsSource;
  /** Sends a parent's decision to the kernel; null until the web app is connected. */
  decide?: ApprovalTransport | null;
  retry?: ReactNode;
};

// The Experiments surface (Issue #37): each experiment's change, its risk,
// whether it can be undone, its approval, where it is in its life, what came
// of it and whether the explanation it tested was promoted. What needs the
// parent comes first. Decisions go to the kernel; this view never changes an
// experiment's state itself.
export function ExperimentsView({ source, decide = null, retry }: ExperimentsViewProps) {
  switch (source.status) {
    case "unconnected":
      return (
        <EmptyState title="No experiments proposed">
          <p>
            Nothing starts without your approval. Each proposal will state the change, how risky it
            is, how to undo it, and what the result would mean. Anything judged unsafe cannot be
            approved.
          </p>
        </EmptyState>
      );
    case "loading":
      return (
        <div className={styles.loading} role="status">
          <span className="visually-hidden">Loading experiments</span>
          <LineMark certainty="unknown" />
          <LineMark certainty="unknown" />
        </div>
      );
    case "error":
      return (
        <EmptyState title="Experiments couldn’t be shown">
          <p>
            What Serene sent did not pass its own checks, so nothing is shown rather than showing
            something wrong. No experiment was started or changed.
          </p>
          {retry ? <p>{retry}</p> : null}
        </EmptyState>
      );
    case "ready":
      if (source.view.experiments.length === 0) {
        return (
          <EmptyState title="No experiments proposed yet">
            <p>Serene has not proposed any experiments. Each one will appear here before anything starts.</p>
          </EmptyState>
        );
      }
      return <Experiments view={source.view} decide={decide} />;
  }
}

function Experiments({ view, decide }: { view: View; decide: ApprovalTransport | null }) {
  return (
    <div className={styles.experiments} data-experiments>
      {GROUPS.map((group) => {
        const members = view.experiments.filter((e) => group.phases.includes(e.phase));
        return (
          <Group key={group.title} title={group.title} count={members.length}>
            {members.length === 0 ? (
              <p className={styles.empty}>{group.empty}</p>
            ) : (
              <ul className={styles.list}>
                {members.map((experiment) => (
                  <li key={experiment.experiment_id}>
                    <ExperimentCard experiment={experiment} decide={decide} />
                  </li>
                ))}
              </ul>
            )}
          </Group>
        );
      })}
    </div>
  );
}

function Group({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  const id = useId();
  return (
    <section className={styles.group} aria-labelledby={id}>
      <h2 id={id} className={styles.groupTitle}>
        {title} <span className={styles.count}>({count})</span>
      </h2>
      {children}
    </section>
  );
}

// Finished well is solid, stopped or blocked is struck, waiting is dotted and
// under way is dashed: the certainty notation, always beside the words.
const PHASE_MARK: Record<ExperimentPhase, Certainty> = {
  PROPOSED: "unknown",
  CLASSIFIED: "unknown",
  AWAITING_APPROVAL: "unknown",
  APPROVED: "observed",
  WAITING_FOR_OUTCOME: "observed",
  OUTCOME_OVERDUE: "observed",
  COMPLETED: "tested",
  BLOCKED: "refuted",
  ABANDONED: "refuted",
  PARKED_UNRESOLVED: "superseded",
};

function ExperimentCard({ experiment, decide }: { experiment: Experiment; decide: ApprovalTransport | null }) {
  const headingId = useId();
  const { intervention, approval } = experiment;
  const safety = experiment.safety_class;
  return (
    <article
      className={styles.card}
      aria-labelledby={headingId}
      data-experiment-id={experiment.experiment_id}
      data-phase={experiment.phase}
      data-safety={safety ?? "UNCLASSIFIED"}
    >
      <p className={styles.state}>
        <LineMark certainty={PHASE_MARK[experiment.phase]} className={styles.stateMark} />
        <span data-phase-label>{PHASE_LABELS[experiment.phase].term}</span>
        <span className={styles.safety} data-safety-label>
          {safety ? `Risk: ${SAFETY_LABELS[safety].term}` : "Risk: not checked yet"}
        </span>
      </p>
      <h3 id={headingId} className={styles.title}>
        {intervention.description}
      </h3>
      <p className={styles.phaseText}>{PHASE_LABELS[experiment.phase].description}</p>

      <dl className={styles.pairs}>
        <Pair term="What it tests">{experiment.hypothesis_statement ?? "Not recorded."}</Pair>
        <Pair term="Kind of change">{CATEGORY_LABELS[intervention.category]}</Pair>
        <Pair term="Can it be undone?">
          {intervention.reversible ? "Yes. It can be stopped and undone at any time." : "No. It could not be undone."}
        </Pair>
        <Pair term="Longest it runs">
          {intervention.max_duration_days} {intervention.max_duration_days === 1 ? "day" : "days"}
        </Pair>
        <Pair term="Effort for your family">{BURDEN_LABELS[intervention.burden]}</Pair>
        <Pair term="Compared with">{experiment.comparison}</Pair>
        <Pair term="Judged by">{experiment.outcome_measure}</Pair>
        <Pair term="Applies in">{experiment.contexts.map(variableLabel).join(", ")}</Pair>
      </dl>

      <section className={styles.block} aria-label="Risk">
        <h4 className={styles.blockTitle}>Risk</h4>
        {safety ? (
          <>
            <p>
              <strong>Risk: {SAFETY_LABELS[safety].term}.</strong> {SAFETY_LABELS[safety].description}
            </p>
            <Reasons codes={experiment.classification_reasons} label="Why it was rated this way" />
          </>
        ) : (
          <p className={styles.empty}>Not checked for safety yet. Nothing can be approved until it is.</p>
        )}
        {experiment.blocked_reasons.length > 0 ? (
          <>
            <p className={styles.subhead}>Why it is blocked</p>
            <Reasons codes={experiment.blocked_reasons} label="Why it is blocked" />
          </>
        ) : null}
      </section>

      <section className={styles.block} aria-label="Approval">
        <h4 className={styles.blockTitle}>Approval</h4>
        {approval ? (
          <dl className={styles.pairs}>
            <Pair term="Decision">{approvalState(approval.state)}</Pair>
            {approval.requested_at ? (
              <Pair term="Asked">
                <Time iso={approval.requested_at} />
              </Pair>
            ) : null}
            <Pair term={approval.decision_open ? "Open until" : "Was open until"}>
              <Time iso={approval.expires_at} />
            </Pair>
            {approval.nudges > 0 ? (
              <Pair term="Reminders">{approval.nudges === 1 ? "One reminder sent" : `${approval.nudges} reminders sent`}</Pair>
            ) : null}
            {approval.decided_at ? (
              <Pair term="Decided">
                <Time iso={approval.decided_at} />
                {approval.decided_via ? ` ${CHANNEL_LABELS[approval.decided_via]}` : null}
              </Pair>
            ) : null}
          </dl>
        ) : (
          <p className={styles.empty}>
            {safety === "RED" ? "Never asked: it cannot be approved." : "You have not been asked yet."}
          </p>
        )}
        {experiment.phase === "AWAITING_APPROVAL" || safety === "RED" ? (
          <DecisionPanel experiment={experiment} decide={decide} />
        ) : null}
      </section>

      <section className={styles.block} aria-label="Timeline">
        <h4 className={styles.blockTitle}>Timeline</h4>
        <ol className={styles.timeline}>
          {experiment.proposed_at ? <Event term="Proposed" iso={experiment.proposed_at} /> : null}
          {experiment.started_at ? <Event term="Started" iso={experiment.started_at} /> : null}
          {experiment.outcome_due_at ? (
            <Event
              term={experiment.phase === "OUTCOME_OVERDUE" ? "Outcome was due" : "Outcome due"}
              iso={experiment.outcome_due_at}
            />
          ) : null}
          {experiment.ended_at ? <Event term="Ended" iso={experiment.ended_at} /> : null}
        </ol>
        {experiment.outcome_timed_out ? (
          <p>No outcome was reported in time, so it was stopped. Nothing was concluded from it.</p>
        ) : null}
        {experiment.abandoned_reasons.length > 0 ? (
          <Reasons codes={experiment.abandoned_reasons} label="Why it was stopped" />
        ) : null}
      </section>

      <section className={styles.block} aria-label="Outcomes">
        <h4 className={styles.blockTitle}>Outcomes</h4>
        {experiment.outcomes.length === 0 ? (
          <p className={styles.empty}>No outcome reported.</p>
        ) : (
          <ul className={styles.outcomes}>
            {experiment.outcomes.map((o) => (
              <li key={o.outcome_id} className={styles.outcome} data-result={o.result}>
                <span className={styles.outcomeResult}>{RESULT_LABELS[o.result]}</span>
                <span>{o.summary}</span>
                <span className={styles.aside}>
                  Reported by {ACTOR_LABELS[o.reported_by].replace(/^A /, "a ")} on{" "}
                  <Time iso={o.reported_at} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.block} aria-label="Promotion result">
        <h4 className={styles.blockTitle}>Promotion result</h4>
        {experiment.promotion ? (
          <>
            <p data-promotion={experiment.promotion.granted ? "granted" : "denied"}>
              {promotionText(experiment.promotion.granted, experiment.promotion.to_level)}
            </p>
            <Reasons codes={experiment.promotion.reason_codes} label="Why" />
          </>
        ) : (
          <p className={styles.empty}>
            {experiment.phase === "COMPLETED" ? "No promotion decision recorded." : "Decided only after it finishes."}
          </p>
        )}
      </section>
    </article>
  );
}

function approvalState(state: NonNullable<Experiment["approval"]>["state"]): string {
  switch (state) {
    case "PENDING":
      return "Waiting for you";
    case "NUDGED":
      return "Waiting for you (reminded)";
    case "GRANTED":
      return "Approved";
    case "REJECTED":
      return "Declined";
    case "PARKED_UNRESOLVED":
      return "Expired without a decision";
  }
}

function Pair({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Time({ iso }: { iso: string }) {
  return <time dateTime={iso}>{formatDate(iso)}</time>;
}

function Event({ term, iso }: { term: string; iso: string }) {
  return (
    <li className={styles.event}>
      <span className={styles.eventTerm}>{term}</span> <Time iso={iso} />
    </li>
  );
}

function Reasons({ codes, label }: { codes: readonly string[]; label: string }) {
  if (codes.length === 0) return null;
  return (
    <ul className={styles.reasons} aria-label={label}>
      {codes.map((code, i) => {
        const reason = explainReason(code);
        return (
          <li key={i} className={styles.reason} data-reason-code={code} data-known={reason.known}>
            <span>{reason.text}</span>
            <code className={styles.refId}>{code}</code>
          </li>
        );
      })}
    </ul>
  );
}
