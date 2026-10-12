import { useId, type ReactNode } from "react";
import styles from "./EmptyState.module.css";

type EmptyStateProps = {
  title: string;
  children: ReactNode;
  /**
   * "waiting": nothing is known yet (a closed bud on a dotted stem).
   * "stopped": something is wrong or ended (the session, a bad payload).
   */
  tone?: "waiting" | "stopped";
  /** Links or buttons that lead out of this state. */
  actions?: ReactNode;
};

// An honest blank. Surfaces render this until real projection state exists;
// it never stands in for data with placeholders. The bud has not opened and
// its stem is dotted, the notation for "not yet known".
export function EmptyState({ title, children, tone = "waiting", actions }: EmptyStateProps) {
  const headingId = useId();
  return (
    <section className={styles.empty} aria-labelledby={headingId} data-tone={tone}>
      <svg className={styles.glyph} viewBox="0 0 48 72" aria-hidden="true" focusable="false">
        {tone === "waiting" ? (
          <>
            <path className={styles.stem} d="M24 70c0-10-3-18 0-30" />
            <path className={styles.leaf} d="M23.2 56c-5-1-9.5-4.5-11-10 5.5.2 9.8 3.4 11 10Z" />
            <path className={styles.bud} d="M24 40c-6.5-3-9-9.5-7.5-16 1.4-6 5.2-10.5 7.5-14 2.3 3.5 6.1 8 7.5 14 1.5 6.5-1 13-7.5 16Z" />
            <path className={styles.sepal} d="M24 40c-3.5-1.5-6-4.5-7-8.5M24 40c3.5-1.5 6-4.5 7-8.5" />
          </>
        ) : (
          <>
            <circle className={styles.ring} cx="24" cy="36" r="16" />
            <path className={styles.bar} d="M17 36h14" />
          </>
        )}
      </svg>
      <div className={styles.body}>
        <h2 id={headingId} className={styles.title}>
          {title}
        </h2>
        {children}
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </div>
    </section>
  );
}
