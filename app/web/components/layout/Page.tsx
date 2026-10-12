import type { ReactNode } from "react";
import { RecordStatus } from "@/components/shell/RecordStatus";
import styles from "./Page.module.css";

type PageProps = {
  title: string;
  /** The one question this surface answers, in the parent's words. */
  question?: string;
  lead: string;
  /**
   * "standard": a working surface. "reading": a single column of text (sign
   * in, errors). "wide": room for a map beside its panel.
   */
  width?: "standard" | "reading" | "wide";
  /** The record status. Surfaces on the signed-in family record pass their own (#87); null shows none. */
  status?: ReactNode;
  children?: ReactNode;
};

// Every surface opens the same way: its name in wide capitals on the ruled
// sheet, the question it answers, what it holds, and, where a survey sheet
// keeps its legend, which family record is open. Then straight into the work:
// the header is a line of context, not a cover page. The bloom belongs to the
// landing page alone.
export function Page({ title, question, lead, width = "standard", status, children }: PageProps) {
  return (
    <div className={styles.page} data-width={width}>
      <header className={styles.head}>
        <div className={styles.heading}>
          <h1 className={styles.title}>{title}</h1>
          {question ? <p className={styles.question}>{question}</p> : null}
          <p className={styles.lead}>{lead}</p>
        </div>
        {status === null ? null : <div className={styles.status}>{status ?? <RecordStatus />}</div>}
      </header>
      <div id="surface-body" className={styles.body}>
        {children}
      </div>
      <p className={styles.colophon}>
        What happened, what Serene remembers and what it believes are kept apart.
      </p>
    </div>
  );
}
