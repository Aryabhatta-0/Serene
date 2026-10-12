import type { CSSProperties, ReactNode } from "react";
import { RecordStatus } from "@/components/shell/RecordStatus";
import styles from "./Page.module.css";

type PageProps = {
  title: string;
  lead: string;
  /** "wide" gives the sheet room for a map; text-only surfaces stay at reading width. */
  width?: "reading" | "wide";
  /** The record status. Surfaces on the signed-in family record pass their own (#87). */
  status?: ReactNode;
  children?: ReactNode;
};

// How many capitals the title has to fit on one line. Long multi-word titles
// are allowed to break onto two, so they are measured by half their length.
function titleMeasure(title: string): number {
  if (title.length <= 14) return title.length;
  const longestWord = Math.max(...title.split(/\s+/).map((word) => word.length));
  return Math.max(longestWord, Math.ceil(title.length / 2));
}

// Every surface opens on the same plate: its title set in wide capitals on
// the ruled sheet, what it is for in the left margin, Serene's promise in the
// right, and the record status where a survey sheet keeps its legend. The
// bloom belongs to the landing page alone.
export function Page({ title, lead, width = "reading", status, children }: PageProps) {
  return (
    <div className={styles.page}>
      <header
        className={styles.hero}
        style={{ "--title-measure": titleMeasure(title) } as CSSProperties}
      >
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.lead}>{lead}</p>
        <p className={styles.tagline}>
          What happened, what Serene remembers and what it believes are kept
          apart.
        </p>
        <div className={styles.status}>
          {status ?? <RecordStatus />}
        </div>
        <a href="#surface-body" className={styles.onward}>
          <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <path d="M8 3v10M4 9l4 4 4-4" />
          </svg>
          <span className="visually-hidden">Read on</span>
        </a>
      </header>
      <div id="surface-body" className={styles.body} data-width={width}>
        {children}
      </div>
    </div>
  );
}
