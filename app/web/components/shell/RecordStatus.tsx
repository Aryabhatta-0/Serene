import styles from "./RecordStatus.module.css";

// Shown wherever no family record is connected: when sign-in is not
// configured, and on surfaces whose data is not streamed yet (Memory #99,
// Causal Twin #75). Signed-in surfaces use RecordControl instead (#87).
// Saying so plainly is part of the product: Serene never implies it knows
// something it has not recorded.
export function RecordStatus() {
  return (
    <p className={styles.status}>
      <svg
        className={styles.ring}
        viewBox="0 0 16 16"
        aria-hidden="true"
        focusable="false"
      >
        <circle cx="8" cy="8" r="6" />
      </svg>
      <span>
        <span className={styles.title}>No family record connected</span>
        <span className={styles.detail}>
          Nothing is shown until Serene has recorded it.
        </span>
      </span>
    </p>
  );
}
