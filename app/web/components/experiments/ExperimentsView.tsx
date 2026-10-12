import { useId, type ReactNode } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { LineMark, type Certainty } from "@/components/notation/LineMark";
import { Icon } from "@/components/system/Icon";
import { Pair, Pairs, Reasons, Time } from "@/components/system/Record";
import { SafetyBadge } from "@/components/system/SafetyBadge";
import { StageTrack } from "@/components/system/StageTrack";
import { variableLabel } from "@/lib/causal-twin/categories";
import { ACTOR_LABELS } from "@/lib/causal-twin/provenance";
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
  lifecycle,
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

export const experimentAnchor = (id: string) => `experiment-${id}`;

// The Experiments surface (Issue #37): a controlled space for deciding what
// to try. Each experiment shows its change, why it is suggested, its safety
// class, whether it can be undone, how long it runs, what will be watched,
// where it is in its life, what came of it and what the Promotion Gate
// decided. What needs the parent comes first. Decisions go to the kernel;
// this view never changes an experiment's state itself.
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
          <LineMark certainty="unknown" />
        </div>
      );
    case "error":
      return (
        <EmptyState title="Experiments couldn’t be shown" tone="stopped" actions={retry}>
          <p>
            What Serene sent did not pass its own checks, so nothing is shown rather than showing
            something wrong. No experiment was started or changed.
          </p>
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
      {GROUPS.map((group, i) => {
        const members = view.experiments.filter((e) => group.phases.includes(e.phase));
        return (
          <Group key={group.title} title={group.title} count={members.length} lead={i === 0}>
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

function Group({ title, count, lead, children }: { title: string; count: number; lead: boolean; children: ReactNode }) {
  const id = useId();
  return (
    <section className={styles.group} aria-labelledby={id} data-lead={lead || undefined} data-empty={count === 0 || undefined}>
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
  const deciding = experiment.phase === "AWAITING_APPROVAL" || safety === "RED";
  const days = intervention.max_duration_days;
  return (
    <article
      id={experimentAnchor(experiment.experiment_id)}
      className={styles.card}
      aria-labelledby={headingId}
      data-experiment-id={experiment.experiment_id}
      data-phase={experiment.phase}
      data-safety={safety ?? "UNCLASSIFIED"}
    >
      <header className={styles.head}>
        <div className={styles.badges}>
          <SafetyBadge safety={safety} labelled />
          <p className={styles.state}>
            <LineMark certainty={PHASE_MARK[experiment.phase]} className={styles.stateMark} />
            <span data-phase-label>{PHASE_LABELS[experiment.phase].term}</span>
          </p>
        </div>
        <h3 id={headingId} className={styles.title}>
          {intervention.description}
        </h3>
        <p className={styles.phaseText}>{PHASE_LABELS[experiment.phase].description}</p>
        <StageTrack label="Where this experiment is" steps={lifecycle(experiment)} className={styles.track} />
      </header>

      <div className={styles.body} data-deciding={deciding || undefined}>
        <div className={styles.spec}>
          <dl className={styles.cells}>
            <Fact icon="undo" term="Can it be undone?" strong={!intervention.reversible}>
              {intervention.reversible ? "Yes. It can be stopped and undone at any time." : "No. It could not be undone."}
            </Fact>
            <Fact icon="clock" term="Longest it runs">
              {days} {days === 1 ? "day" : "days"}
            </Fact>
            <Fact icon="weight" term="Effort for your family">
              {BURDEN_LABELS[intervention.burden]}
            </Fact>
            <Fact icon="flask" term="Kind of change">
              {CATEGORY_LABELS[intervention.category]}
            </Fact>
          </dl>

          <Pairs>
            <Pair term="Why it is suggested">
              {experiment.hypothesis_statement ? (
                <>It tests one explanation: “{experiment.hypothesis_statement}”</>
              ) : (
                "Not recorded."
              )}
            </Pair>
            <Pair term="Compared with">{experiment.comparison}</Pair>
            <Pair term="What will be watched">{experiment.outcome_measure}</Pair>
            <Pair term="Applies in">{experiment.contexts.map(variableLabel).join(", ")}</Pair>
          </Pairs>

          <section className={styles.block} aria-label="Risk">
            <h4 className={styles.blockTitle}>Risk</h4>
            {safety ? (
              <>
                <p>
                  <strong>
                    {safety} · {SAFETY_LABELS[safety].term}.
                  </strong>{" "}
                  {SAFETY_LABELS[safety].description}
                </p>
                <Reasons codes={experiment.classification_reasons} label="Why it was rated this way" explain={explainReason} />
              </>
            ) : (
              <p className={styles.empty}>Not checked for safety yet. Nothing can be approved until it is.</p>
            )}
            {experiment.blocked_reasons.length > 0 ? (
              <>
                <p className={styles.subhead}>Why it is blocked</p>
                <Reasons codes={experiment.blocked_reasons} label="Why it is blocked" explain={explainReason} tone="against" />
              </>
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
                    <span className={styles.outcomeResult}>
                      <LineMark
                        certainty={o.result === "SUPPORTS" ? "tested" : o.result === "CONTRADICTS" ? "refuted" : "unknown"}
                        className={styles.outcomeMark}
                      />
                      {RESULT_LABELS[o.result]}
                    </span>
                    <span>{o.summary}</span>
                    <span className={styles.aside}>
                      Reported by {ACTOR_LABELS[o.reported_by].replace(/^A /, "a ")} on <Time iso={o.reported_at} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={styles.block} aria-label="Promotion result" data-gate={experiment.promotion ? (experiment.promotion.granted ? "granted" : "denied") : "pending"}>
            <h4 className={styles.blockTitle}>Promotion result</h4>
            {experiment.promotion ? (
              <>
                <p className={styles.gate} data-promotion={experiment.promotion.granted ? "granted" : "denied"}>
                  <span className={styles.gateMark} aria-hidden="true">
                    <Icon name={experiment.promotion.granted ? "check" : "cross"} />
                  </span>
                  <span>{promotionText(experiment.promotion.granted, experiment.promotion.to_level)}</span>
                </p>
                <Reasons codes={experiment.promotion.reason_codes} label="Why" explain={explainReason} />
              </>
            ) : (
              <p className={styles.empty}>
                {experiment.phase === "COMPLETED"
                  ? "No promotion decision recorded."
                  : "The Promotion Gate decides only after it finishes."}
              </p>
            )}
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
              <Reasons codes={experiment.abandoned_reasons} label="Why it was stopped" explain={explainReason} tone="against" />
            ) : null}
          </section>
        </div>

        <section className={styles.approval} aria-label="Approval">
          <h4 className={styles.blockTitle}>Approval</h4>
          {approval ? (
            <Pairs>
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
            </Pairs>
          ) : (
            <p className={styles.empty}>
              {safety === "RED" ? "Never asked: it cannot be approved." : "You have not been asked yet."}
            </p>
          )}
          {deciding ? <DecisionPanel experiment={experiment} decide={decide} /> : null}
        </section>
      </div>
    </article>
  );
}

function Fact({
  icon,
  term,
  strong = false,
  children,
}: {
  icon: "undo" | "clock" | "weight" | "flask";
  term: string;
  strong?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={styles.cell} data-strong={strong || undefined}>
      <dt>
        <Icon name={icon} className={styles.cellIcon} />
        {term}
      </dt>
      <dd>{children}</dd>
    </div>
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

function Event({ term, iso }: { term: string; iso: string }) {
  return (
    <li className={styles.event}>
      <span className={styles.eventTerm}>{term}</span> <Time iso={iso} />
    </li>
  );
}
