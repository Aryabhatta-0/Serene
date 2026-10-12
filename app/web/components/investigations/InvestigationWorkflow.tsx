import { useId } from "react";
import { Reasons } from "@/components/system/Record";
import type { Investigation } from "@/lib/investigations/model";
import { explainReason, nextActionText, PHASE_LABELS } from "@/lib/investigations/present";
import styles from "./InvestigationWorkflow.module.css";

const recordedTime = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
});

/** Persisted phase visits, including loops and stops. Never an inferred execution log. */
export function InvestigationWorkflow({ investigation: inv, headingLevel: Heading = "h3" }: {
  investigation: Investigation;
  headingLevel?: "h3" | "h4";
}) {
  const id = useId();
  const history = inv.phase_history ?? [];
  const current = history[history.length - 1];
  const stopped = inv.phase === "PARKED_UNRESOLVED";
  const finished = inv.phase === "COMPLETE";
  const waiting = inv.next_action.kind === "WAIT_FOR_PARENT_ANSWER" || inv.next_action.kind === "WAIT_FOR_APPROVAL";
  const status = stopped ? "Paused without an answer" : finished ? "Finished" : waiting ? "Waiting for you" : "Current recorded stage";
  return (
    <section className={styles.workflow} aria-labelledby={id} data-block="workflow">
      <Heading id={id} className={styles.heading}>Recorded workflow</Heading>
      <div className={styles.current} role="status" aria-live="polite" aria-atomic="true">
        <strong>{status}</strong>
        {PHASE_LABELS[inv.phase] !== status ? <span>{PHASE_LABELS[inv.phase]}</span> : null}
        <p>{nextActionText(inv.next_action).title}</p>
      </div>
      {history.length === 0 ? (
        <p className={styles.note}>Earlier steps were not included in this record. Only the current stage is available.</p>
      ) : (
        <details className={styles.history} open>
          <summary>Steps Serene actually took</summary>
          <p className={styles.note}>Shown in recorded order. A step can repeat when Serene needs more evidence. Times are when each step was saved.</p>
          <ol className={styles.steps} aria-label="Recorded investigation steps">
            {history.map((step) => {
              const latest = step.sequence === current.sequence;
              return (
                <li key={step.sequence} data-workflow-sequence={step.sequence} data-workflow-phase={step.phase}
                  data-latest={latest || undefined} aria-current={latest ? "step" : undefined}>
                  <span className={styles.marker} aria-hidden="true" />
                  <div className={styles.body}>
                    <div className={styles.stepHead}>
                      <strong>{PHASE_LABELS[step.phase]}</strong>
                      <span className={styles.state}>{latest ? status : "Recorded"}</span>
                      <time dateTime={step.recorded_at}>{recordedTime.format(new Date(step.recorded_at))} UTC</time>
                    </div>
                    <Reasons codes={step.reason_codes} label="Why this step was recorded" explain={explainReason} />
                  </div>
                </li>
              );
            })}
          </ol>
        </details>
      )}
    </section>
  );
}
