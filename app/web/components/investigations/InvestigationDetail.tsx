import { useId, type ReactNode } from "react";
import { LineMark, type Certainty } from "@/components/notation/LineMark";
import { formatDate } from "@/lib/causal-twin/provenance";
import type { Hypothesis, Investigation } from "@/lib/investigations/model";
import {
  CHANNEL_LABELS,
  CHECK_LABELS,
  EVIDENCE_KIND_LABELS,
  HYPOTHESIS_STATUS_LABELS,
  LEVEL_LABELS,
  PHASE_LABELS,
  REQUEST_STATUS_LABELS,
  UNCERTAINTY_TEXT,
  VALUE_LABELS,
  VERIFICATION_LABELS,
  explainReason,
  nextActionText,
  sourceText,
} from "@/lib/investigations/present";
import styles from "./Investigations.module.css";

const HYPOTHESIS_MARK: Record<Hypothesis["status"], Certainty> = {
  ACTIVE: "unknown",
  REFUTED: "refuted",
  SUPERSEDED: "superseded",
};

export const investigationAnchor = (id: string) => `investigation-${id}`;

type Props = { investigation: Investigation; headingLevel?: "h2" | "h3" };

// One investigation (Issue #35): where it stands, what Serene will do next
// (the kernel's next action, never decided here), what it does not know yet,
// the explanations it is weighing, the evidence still missing with the source
// chosen for it, and how the evidence that arrived was checked.
export function InvestigationDetail({ investigation: inv, headingLevel: Heading = "h3" }: Props) {
  const headingId = useId();
  const action = nextActionText(inv.next_action);
  const open = inv.evidence_requests.filter((r) => r.status === "OPEN");
  const received = inv.evidence_requests.flatMap((r) => r.evidence.map((e) => ({ e, r })));
  const openQuestion = open[open.length - 1] ?? null;
  return (
    <article
      id={investigationAnchor(inv.investigation_id)}
      className={styles.investigation}
      aria-labelledby={headingId}
      data-investigation-id={inv.investigation_id}
      data-phase={inv.phase}
    >
      <p className={styles.state}>
        <span data-phase-label>{PHASE_LABELS[inv.phase]}</span>
        <span className={styles.opened}>
          Opened <time dateTime={inv.opened_at}>{formatDate(inv.opened_at)}</time>
        </span>
      </p>
      <Heading id={headingId} className={styles.question}>
        {inv.question}
      </Heading>

      <Block title="What Serene will do next" name="next-action" strong>
        <p className={styles.nextTitle} data-next-action={inv.next_action.kind}>
          {action.title}
        </p>
        {action.detail ? <p className={styles.nextDetail}>{action.detail}</p> : null}
        {inv.next_action.reason_codes.length > 0 ? <Reasons codes={inv.next_action.reason_codes} label="Why it stopped" /> : null}
      </Block>

      <Block title="What Serene doesn’t know yet" name="uncertainty">
        {inv.uncertainty.length === 0 ? (
          <p className={styles.empty}>Serene recorded no open uncertainty for this question.</p>
        ) : (
          <ul className={styles.facts}>
            {inv.uncertainty.map((fact) => (
              <li key={fact} data-uncertainty={fact}>
                {UNCERTAINTY_TEXT[fact]}
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Block title="Explanations being weighed" name="hypotheses">
        {inv.hypotheses.length === 0 ? (
          <p className={styles.empty}>No explanation has been formed yet.</p>
        ) : (
          <ul className={styles.hypotheses}>
            {inv.hypotheses.map((h) => {
              const prediction = openQuestion?.predictions.find((p) => p.hypothesis_id === h.hypothesis_id);
              return (
                <li key={h.hypothesis_id} className={styles.hypothesis} data-hypothesis-status={h.status}>
                  <p className={styles.hypothesisState}>
                    <LineMark certainty={HYPOTHESIS_MARK[h.status]} className={styles.mark} />
                    <span>{HYPOTHESIS_STATUS_LABELS[h.status]}</span>
                    {h.level ? <span className={styles.level}>{LEVEL_LABELS[h.level]}</span> : null}
                  </p>
                  <p className={styles.statement}>{h.statement}</p>
                  {prediction && openQuestion?.question ? (
                    <p className={styles.aside}>
                      If this is right, the answer to the open question would be{" "}
                      <strong>{prediction.expected === "YES" ? "yes" : "no"}</strong>.
                    </p>
                  ) : null}
                  {h.falsification_criteria.length > 0 ? (
                    <p className={styles.aside}>What would rule it out: {h.falsification_criteria.join("; ")}.</p>
                  ) : null}
                  {h.known_confounders.length > 0 ? (
                    <p className={styles.aside}>What could confuse it: {h.known_confounders.join("; ")}.</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </Block>

      <Block title="Evidence still missing" name="missing-evidence">
        {open.length === 0 ? (
          <p className={styles.empty}>Nothing is being asked for right now.</p>
        ) : (
          <ul className={styles.requests}>
            {open.map((r) => (
              <li key={r.request_id} className={styles.request} data-request-id={r.request_id}>
                <p className={styles.statement}>{r.question ?? r.requested_fields.map((f) => f.replace(/_+/g, " ")).join(", ")}</p>
                <dl className={styles.pairs}>
                  <div>
                    <dt>Source chosen</dt>
                    <dd data-selected-source={r.acquisition_mode ?? "NONE"}>
                      {sourceText(r.acquisition_mode, r.allowed_domains, r.subject)}
                    </dd>
                  </div>
                  <div>
                    <dt>Why this</dt>
                    <dd>{r.rationale}</dd>
                  </div>
                  <div>
                    <dt>How much it would tell</dt>
                    <dd>{VALUE_LABELS[r.information_value]}</dd>
                  </div>
                  {r.failed_attempts > 0 ? (
                    <div>
                      <dt>Attempts that failed</dt>
                      <dd>{r.failed_attempts}</dd>
                    </div>
                  ) : null}
                </dl>
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Block title="Evidence received and how it was checked" name="verification">
        {received.length === 0 ? (
          <p className={styles.empty}>No evidence has arrived for this question yet.</p>
        ) : (
          <ul className={styles.requests}>
            {received.map(({ e, r }) => (
              <li key={e.evidence_id} className={styles.request} data-verification={e.verification_status}>
                <p className={styles.statement}>
                  {EVIDENCE_KIND_LABELS[e.kind]} {CHANNEL_LABELS[e.source_kind]}
                  {r.question ? <span className={styles.aside}> to “{r.question}”</span> : null}
                </p>
                <p>
                  <strong>{VERIFICATION_LABELS[e.verification_status]}.</strong>{" "}
                  <span className={styles.aside}>{REQUEST_STATUS_LABELS[r.status]}</span>
                </p>
                {e.checks_passed.length > 0 ? (
                  <ul className={styles.checks} aria-label="Checks it passed">
                    {e.checks_passed.map((c) => (
                      <li key={c}>{CHECK_LABELS[c]}</li>
                    ))}
                  </ul>
                ) : null}
                {e.rejection_reason_codes.length > 0 ? <Reasons codes={e.rejection_reason_codes} label="Why it failed" /> : null}
              </li>
            ))}
          </ul>
        )}
      </Block>
    </article>
  );
}

function Block({ title, name, strong, children }: { title: string; name: string; strong?: boolean; children: ReactNode }) {
  const id = useId();
  return (
    <section className={strong ? styles.next : styles.block} aria-labelledby={id} data-block={name}>
      <h4 id={id} className={styles.blockTitle}>
        {title}
      </h4>
      {children}
    </section>
  );
}

function Reasons({ codes, label }: { codes: readonly string[]; label: string }) {
  return (
    <ul className={styles.reasons} aria-label={label}>
      {codes.map((code, i) => {
        const reason = explainReason(code);
        return (
          <li key={i} className={styles.reason} data-reason-code={code} data-known={reason.known}>
            <span>{reason.text}</span>
            <code className={styles.code}>{code}</code>
          </li>
        );
      })}
    </ul>
  );
}
