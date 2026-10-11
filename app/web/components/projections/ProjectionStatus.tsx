import type { ProjectionsState } from "@/lib/projections/useProjections";
import styles from "./ProjectionStatus.module.css";

// How current what the parent sees is (Issue #33), always in words. "Live" is
// shown only while the Realtime subscription is up and the snapshot is in.
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
      {TEXT[state.status]}
    </p>
  );
}
