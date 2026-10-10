import { LineMark } from "@/components/notation/LineMark";
import styles from "./SurfaceLoading.module.css";

// Loading keeps the page's shape so nothing jumps when state arrives. The
// placeholder strokes are dotted: while loading, nothing is known yet.
export function SurfaceLoading() {
  return (
    <div className={styles.loading} role="status">
      <span className="visually-hidden">Loading</span>
      <div className={styles.header} aria-hidden="true">
        <LineMark certainty="unknown" className={styles.title} />
        <LineMark certainty="unknown" className={styles.lead} />
        <LineMark certainty="unknown" className={styles.leadShort} />
      </div>
      <div className={styles.body} aria-hidden="true">
        <LineMark certainty="unknown" className={styles.row} />
        <LineMark certainty="unknown" className={styles.row} />
        <LineMark certainty="unknown" className={styles.rowShort} />
      </div>
    </div>
  );
}
