import styles from "./RecordStatus.module.css";

// The shell is not connected to any family record yet (projection streaming
// arrives with Issue #33). Saying so plainly is part of the product: Serene
// never implies it knows something it has not recorded.
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
