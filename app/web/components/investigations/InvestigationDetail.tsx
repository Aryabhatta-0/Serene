import { useId, type ReactNode } from "react";
import { LineMark, type Certainty } from "@/components/notation/LineMark";
import { Icon, type IconName } from "@/components/system/Icon";
import { LevelLadder } from "@/components/system/LevelLadder";
import { Onward, Pair, Pairs, Reasons, Time } from "@/components/system/Record";
import { StageTrack } from "@/components/system/StageTrack";
import type { EvidenceItem, Hypothesis, Investigation, NextActionKind } from "@/lib/investigations/model";
import {
  CHANNEL_LABELS,
  CHECK_LABELS,
  EVIDENCE_KIND_LABELS,
  HYPOTHESIS_STATUS_LABELS,
  LEVEL_LABELS,
  LEVEL_NUMBERS,
  PHASE_LABELS,
  REQUEST_STATUS_LABELS,
  UNCERTAINTY_TEXT,
  VALUE_LABELS,
  VERIFICATION_LABELS,
  explainReason,
  investigationStages,
  nextActionText,
  sourceText,
} from "@/lib/investigations/present";
import styles from "./Investigations.module.css";

const HYPOTHESIS_MARK: Record<Hypothesis["status"], Certainty> = {
  ACTIVE: "unknown",
  REFUTED: "refuted",
  SUPERSEDED: "superseded",
};

const VERIFICATION_ICON: Record<EvidenceItem["verification_status"], IconName> = {
  VERIFIED: "check",
  REJECTED: "cross",
  UNVERIFIED: "ring",
  NOT_APPLICABLE: "ring",
};

const NEXT_ICON: Partial<Record<NextActionKind, IconName>> = {
  WAIT_FOR_PARENT_ANSWER: "ask",
  PROCESS_ANSWER: "ask",
  RESEARCH: "search",
  CHOOSE_EVIDENCE: "search",
  VERIFY_EVIDENCE: "check",
  WAIT_FOR_APPROVAL: "hand",
  FORM_HYPOTHESES: "branch",
};

export const investigationAnchor = (id: string) => `investigation-${id}`;

type Props = {
  investigation: Investigation;
  headingLevel?: "h2" | "h3";
  /**
   * "workspace": the full investigation (Investigations). "brief": the same
   * record, read at a glance (Today): the same facts, fewer asides.
   */
  variant?: "workspace" | "brief";
};

// One investigation (Issue #35): what happened, the explanations being
// weighed and what would tell them apart, the evidence still missing (with
// the source chosen for it), how the evidence that arrived was checked, what
// Serene doesn't know, and what it will do next. The next action is the
// kernel's, never decided here; uncertainty is the kernel's list of facts,
// never a score.
export function InvestigationDetail({ investigation: inv, headingLevel: Heading = "h3", variant = "workspace" }: Props) {
  const headingId = useId();
  const brief = variant === "brief";
  const open = inv.evidence_requests.filter((r) => r.status === "OPEN");
  const received = inv.evidence_requests.flatMap((r) => r.evidence.map((e) => ({ e, r })));
  const openQuestion = open[open.length - 1] ?? null;
  const live = inv.hypotheses.filter((h) => h.status === "ACTIVE").length;
  return (
    <article
      id={investigationAnchor(inv.investigation_id)}
      className={styles.investigation}
      aria-labelledby={headingId}
      data-investigation-id={inv.investigation_id}
      data-phase={inv.phase}
      data-variant={variant}
    >
      <header className={styles.incident}>
        <p className={styles.state}>
          <span data-phase-label>{PHASE_LABELS[inv.phase]}</span>
          <span className={styles.opened}>
            Opened <Time iso={inv.opened_at} />
          </span>
        </p>
        <Heading id={headingId} className={styles.question}>
          {inv.question}
        </Heading>
        <StageTrack
          label="Where this investigation stands"
          steps={investigationStages(inv)}
                    className={styles.track}
        />
      </header>

      <div className={styles.workspace}>
        <div className={styles.rail}>
          <NextAction inv={inv} brief={brief} />

          <Block title="What Serene doesn’t know yet" name="uncertainty">
            {inv.uncertainty.length === 0 ? (
              <p className={styles.empty}>Serene recorded no open uncertainty for this question.</p>
            ) : (
              <ul className={styles.facts}>
                {inv.uncertainty.map((fact) => (
                  <li key={fact} data-uncertainty={fact}>
                    <LineMark certainty="unknown" orientation="vertical" className={styles.factMark} />
                    <span>{UNCERTAINTY_TEXT[fact]}</span>
                  </li>
                ))}
              </ul>
            )}
          </Block>
        </div>

        <div className={styles.main}>
          <Block
            title="Explanations being weighed"
            name="hypotheses"
            note={
              live >= 2
                ? "Serene keeps every explanation that still fits. None is picked until the evidence decides."
                : undefined
            }
          >
            {inv.hypotheses.length === 0 ? (
              <p className={styles.empty}>No explanation has been formed yet.</p>
            ) : (
              <>
                {openQuestion?.question && openQuestion.predictions.length > 0 ? (
                  <p className={styles.decider}>
                    <Icon name="ask" className={styles.deciderIcon} />
                    <span>
                      <span className={styles.deciderTerm}>The open question tells them apart</span>
                      <span className={styles.deciderText}>“{openQuestion.question}”</span>
                    </span>
                  </p>
                ) : null}
                <ul className={styles.hypotheses} data-count={inv.hypotheses.length}>
                  {inv.hypotheses.map((h) => {
                    const prediction = openQuestion?.predictions.find((p) => p.hypothesis_id === h.hypothesis_id);
                    return (
                      <li key={h.hypothesis_id} className={styles.hypothesis} data-hypothesis-status={h.status}>
                        <p className={styles.hypothesisState}>
                          <LineMark certainty={HYPOTHESIS_MARK[h.status]} className={styles.mark} />
                          <span>{HYPOTHESIS_STATUS_LABELS[h.status]}</span>
                        </p>
                        <p className={styles.statement}>{h.statement}</p>
                        {h.level ? (
                          <LevelLadder level={LEVEL_NUMBERS[h.level]} className={styles.level}>
                            {LEVEL_LABELS[h.level]}
                          </LevelLadder>
                        ) : null}
                        {prediction && openQuestion?.question ? (
                          <p className={styles.prediction} data-expected={prediction.expected}>
                            If this is right, the answer to the open question would be{" "}
                            <strong>{prediction.expected === "YES" ? "yes" : "no"}</strong>.
                          </p>
                        ) : null}
                        {!brief && h.falsification_criteria.length > 0 ? (
                          <p className={styles.aside}>
                            <span className={styles.asideTerm}>What would rule it out</span>{" "}
                            {h.falsification_criteria.join("; ")}.
                          </p>
                        ) : null}
                        {!brief && h.known_confounders.length > 0 ? (
                          <p className={styles.aside}>
                            <span className={styles.asideTerm}>What could confuse it</span>{" "}
                            {h.known_confounders.join("; ")}.
                          </p>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
          </Block>

          <Block title="Evidence still missing" name="missing-evidence">
            {open.length === 0 ? (
              <p className={styles.empty}>Nothing is being asked for right now.</p>
            ) : (
              <ul className={styles.requests}>
                {open.map((r) => (
                  <li key={r.request_id} className={styles.request} data-request-id={r.request_id}>
                    <Icon name={r.acquisition_mode === "BROWSE" ? "search" : "ask"} className={styles.requestIcon} />
                    <div className={styles.requestBody}>
                      <p className={styles.statement}>
                        {r.question ?? r.requested_fields.map((f) => f.replace(/_+/g, " ")).join(", ")}
                      </p>
                      {brief ? (
                        <p className={styles.aside} data-selected-source={r.acquisition_mode ?? "NONE"}>
                          {sourceText(r.acquisition_mode, r.allowed_domains, r.subject)}
                        </p>
                      ) : (
                        <Pairs>
                          <Pair term="Source chosen">
                            <span data-selected-source={r.acquisition_mode ?? "NONE"}>
                              {sourceText(r.acquisition_mode, r.allowed_domains, r.subject)}
                            </span>
                          </Pair>
                          <Pair term="Why this">{r.rationale}</Pair>
                          <Pair term="How much it would tell">{VALUE_LABELS[r.information_value]}</Pair>
                          {r.failed_attempts > 0 ? <Pair term="Attempts that failed">{r.failed_attempts}</Pair> : null}
                        </Pairs>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Block>

          <Block title="Evidence received and how it was checked" name="verification">
            {received.length === 0 ? (
              <p className={styles.empty}>No evidence has arrived for this question yet.</p>
            ) : (
              <ul className={styles.received}>
                {received.map(({ e, r }) => (
                  <li key={e.evidence_id} className={styles.evidence} data-verification={e.verification_status}>
                    <p className={styles.evidenceHead}>
                      <span className={styles.verdict} data-status={e.verification_status}>
                        <Icon name={VERIFICATION_ICON[e.verification_status]} />
                        {VERIFICATION_LABELS[e.verification_status]}
                      </span>
                      <span className={styles.evidenceWhat}>
                        {EVIDENCE_KIND_LABELS[e.kind]} {CHANNEL_LABELS[e.source_kind]}
                      </span>
                    </p>
                    {r.question ? <p className={styles.aside}>In answer to “{r.question}” · {REQUEST_STATUS_LABELS[r.status]}</p> : (
                      <p className={styles.aside}>{REQUEST_STATUS_LABELS[r.status]}</p>
                    )}
                    {e.checks_passed.length > 0 ? (
                      <ul className={styles.checks} aria-label="Checks it passed">
                        {e.checks_passed.map((c) => (
                          <li key={c}>
                            <Icon name="check" className={styles.checkIcon} />
                            {CHECK_LABELS[c]}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {e.rejection_reason_codes.length > 0 ? (
                      <Reasons codes={e.rejection_reason_codes} label="Why it failed" explain={explainReason} tone="against" />
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </Block>
        </div>
      </div>
    </article>
  );
}

function NextAction({ inv, brief }: { inv: Investigation; brief: boolean }) {
  const id = useId();
  const action = nextActionText(inv.next_action);
  const kind = inv.next_action.kind;
  const icon = NEXT_ICON[kind] ?? "ring";
  return (
    <section className={styles.next} aria-labelledby={id} data-block="next-action" data-kind={kind}>
      <h4 id={id} className={styles.nextLabel}>
        <Icon name={icon} className={styles.nextIcon} />
        What Serene will do next
      </h4>
      <p className={styles.nextTitle} data-next-action={kind}>
        {action.title}
      </p>
      {action.detail ? <p className={styles.nextDetail}>{action.detail}</p> : null}
      {inv.next_action.reason_codes.length > 0 ? (
        <Reasons codes={inv.next_action.reason_codes} label="Why it stopped" explain={explainReason} />
      ) : null}
      {kind === "WAIT_FOR_APPROVAL" ? (
        <p className={styles.nextOnward}>
          <Onward href="/experiments">Review it in Experiments</Onward>
        </p>
      ) : brief ? (
        <p className={styles.nextOnward}>
          <Onward href={`/investigations#${investigationAnchor(inv.investigation_id)}`}>See the whole investigation</Onward>
        </p>
      ) : null}
    </section>
  );
}

function Block({
  title,
  name,
  note,
  children,
}: {
  title: string;
  name: string;
  note?: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section className={styles.block} aria-labelledby={id} data-block={name}>
      <div className={styles.blockHead}>
        <h4 id={id} className={styles.blockTitle}>
          {title}
        </h4>
        {note ? <p className={styles.blockNote}>{note}</p> : null}
      </div>
      {children}
    </section>
  );
}
