import { LineMark } from "@/components/notation/LineMark";
import styles from "./SurfaceLoading.module.css";

// Loading keeps the page's shape so nothing jumps when state arrives. The
// placeholder strokes are dotted: while loading, nothing is known yet.
export function SurfaceLoading() {
  return (
    <div className={styles.loading} role="status">
      <span className="visually-hidden">Loading</span>
      <div className={styles.group} aria-hidden="true">
        <LineMark certainty="unknown" className={styles.title} />
        <LineMark certainty="unknown" className={styles.lead} />
        <LineMark certainty="unknown" className={styles.leadShort} />
      </div>
      <div className={styles.group} aria-hidden="true">
        <LineMark certainty="unknown" />
        <LineMark certainty="unknown" />
        <LineMark certainty="unknown" className={styles.rowShort} />
      </div>
    </div>
  );
}
