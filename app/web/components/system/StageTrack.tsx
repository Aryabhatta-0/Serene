import type { ReactNode } from "react";
import styles from "./StageTrack.module.css";

// Where something is in its life, drawn in the certainty notation: a stage
// already passed is joined by a solid line, the stage it is in is ringed, the
// stages ahead are dotted, and a stage where it stopped is struck. The track
// only draws the state it is given (a phase from the kernel's projection); it
// never moves ahead of Serene's record.

export type StepState = "done" | "current" | "upcoming" | "stopped";

export type Step = {
  key: string;
  label: string;
  state: StepState;
  /** Optional words under the step (wide tracks only show them). */
  detail?: ReactNode;
};

const SPOKEN: Record<StepState, string> = {
  done: "passed",
  current: "now",
  upcoming: "not reached",
  stopped: "stopped here",
};

type StageTrackProps = {
  label: string;
  steps: readonly Step[];
  /** "full": every label shown. "compact": only the current step is named. */
  density?: "full" | "compact";
  className?: string;
};

export function StageTrack({ label, steps, density = "full", className }: StageTrackProps) {
  const current = steps.find((s) => s.state === "current" || s.state === "stopped");
  return (
    <div className={[styles.wrap, className].filter(Boolean).join(" ")} data-density={density}>
      <ol className={styles.track} aria-label={label}>
        {steps.map((step, i) => (
          <li
            // A step that changes state remounts, so the change is drawn as it lands.
            key={`${step.key}:${step.state}`}
            className={styles.step}
            data-state={step.state}
            data-last={i === steps.length - 1 || undefined}
            aria-current={step.state === "current" ? "step" : undefined}
          >
            <span className={styles.rail} aria-hidden="true">
              <span className={styles.marker} />
              {i < steps.length - 1 ? <span className={styles.line} data-next={steps[i + 1].state} /> : null}
            </span>
            <span className={styles.label}>
              {step.label}
              <span className="visually-hidden">{`: ${SPOKEN[step.state]}`}</span>
            </span>
            {step.detail ? <span className={styles.detail}>{step.detail}</span> : null}
          </li>
        ))}
      </ol>
      {current ? (
        <p className={styles.now} aria-hidden="true" data-state={current.state}>
          {current.label}
        </p>
      ) : null}
    </div>
  );
}
