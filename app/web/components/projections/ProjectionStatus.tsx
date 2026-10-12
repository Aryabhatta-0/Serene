import type { ProjectionsState } from "@/lib/projections/useProjections";
import styles from "./ProjectionStatus.module.css";

// How current what the parent sees is (Issue #33), always in words, with the
// ring drawn in the certainty notation beside them: solid while live, dashed
// while reconnecting, dotted while nothing is connected yet, struck on error.
// "Live" is shown only while the Realtime subscription is up and the snapshot
// is in.
const TEXT: Record<ProjectionsState["status"], string> = {
  unconnected: "Not connected to a family record.",
  connecting: "Connecting to Serene…",
  live: "Live: up to date with Serene’s record.",
  reconnecting: "Reconnecting. Showing what Serene last sent, which may be out of date.",
  error: "Serene’s state could not be read, so nothing is shown.",
};

export function ProjectionStatus({ state }: { state: ProjectionsState }) {
  return (
    <p role="status" className={styles.status} data-sync={state.status}>
      <svg className={styles.ring} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <circle cx="8" cy="8" r="5.5" />
        {state.status === "live" ? <circle className={styles.core} cx="8" cy="8" r="2.25" /> : null}
        {state.status === "error" ? <path className={styles.strike} d="m3.5 12.5 9-9" /> : null}
      </svg>
      <span>{TEXT[state.status]}</span>
    </p>
  );
}
