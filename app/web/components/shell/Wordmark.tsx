import Link from "next/link";
import styles from "./Wordmark.module.css";

// The Serene mark: three strokes that settle from dotted to solid, the same
// notation the product uses for how firmly something is known.
export function Wordmark({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link href="/today" className={styles.wordmark} onClick={onNavigate}>
      <svg
        className={styles.mark}
        viewBox="0 0 22 16"
        aria-hidden="true"
        focusable="false"
      >
        <line x1="2" y1="3" x2="20" y2="3" className={styles.dotted} />
        <line x1="2" y1="8" x2="20" y2="8" className={styles.dashed} />
        <line x1="2" y1="13" x2="20" y2="13" className={styles.solid} />
      </svg>
      <span className={styles.name}>Serene</span>
    </Link>
  );
}
