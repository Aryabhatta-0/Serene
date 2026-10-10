import type { ReactNode } from "react";
import { LineMark } from "@/components/notation/LineMark";
import styles from "./EmptyState.module.css";

type EmptyStateProps = {
  title: string;
  children: ReactNode;
};

// An honest blank: the dotted stroke is the notation for "not yet known".
// Surfaces render this until real projection state exists; it never stands
// in for data with placeholders.
export function EmptyState({ title, children }: EmptyStateProps) {
  const headingId = `empty-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section className={styles.empty} aria-labelledby={headingId}>
      <span className={styles.line}>
        <LineMark certainty="unknown" orientation="vertical" />
      </span>
      <div className={styles.body}>
        <h2 id={headingId} className={styles.title}>
          {title}
        </h2>
        <div className={styles.text}>{children}</div>
      </div>
    </section>
  );
}
