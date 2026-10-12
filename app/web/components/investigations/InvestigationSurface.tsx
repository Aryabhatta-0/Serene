"use client";

import type { ReactNode } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { LineMark } from "@/components/notation/LineMark";
import { ProjectionStatus } from "@/components/projections/ProjectionStatus";
import { TodayBrief } from "@/components/today/TodayBrief";
import { current, parseInvestigations, type Investigation } from "@/lib/investigations/model";
import { PHASE_LABELS } from "@/lib/investigations/present";
import type { ProjectionFeed } from "@/lib/projections/sync";
import { useProjections } from "@/lib/projections/useProjections";
import { InvestigationDetail, investigationAnchor } from "./InvestigationDetail";
import styles from "./Investigations.module.css";

type Props = {
  /** The live projection feed (#33); null unless a parent is signed in with a child chosen (#87). */
  feed: ProjectionFeed | null;
  childId: string | null;
  /** "today": the current investigation, read at a glance. "all": every investigation. */
  mode: "today" | "all";
  /** What to show while nothing is connected (each surface words its own). */
  unconnected: ReactNode;
};

// Today and Investigations (Issue #35), read from the `investigations`
// projection over the Realtime projection path (#33). Nothing here reads the
// ledger, and nothing here decides what Serene does next.
export function InvestigationSurface({ feed, childId, mode, unconnected }: Props) {
  const state = useProjections(feed, childId);
  if (state.status === "unconnected") return <>{unconnected}</>;
  if (state.status === "connecting") {
    return (
      <div className={styles.loading} role="status">
        <span className="visually-hidden">Connecting to Serene</span>
        <LineMark certainty="unknown" />
        <LineMark certainty="unknown" />
        <LineMark certainty="unknown" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <EmptyState title="Serene’s state couldn’t be read" tone="stopped">
        <p>Nothing is shown rather than showing something wrong. Nothing in your family’s record was changed.</p>
      </EmptyState>
    );
  }

  let investigations: Investigation[];
  try {
    investigations = parseInvestigations(state.projections.investigations?.state ?? {});
  } catch {
    return (
      <EmptyState title="Serene’s state couldn’t be read" tone="stopped">
        <p>What Serene sent did not pass its own checks, so nothing is shown.</p>
      </EmptyState>
    );
  }

  const status = <ProjectionStatus state={state} />;
  if (mode === "today") {
    return (
      <TodayBrief
        current={current(investigations)}
        investigations={investigations}
        projections={state.projections}
        status={status}
      />
    );
  }

  if (investigations.length === 0) {
    return (
      <>
        {status}
        <EmptyState title="No open investigations">
          <p>Nothing is being looked into. An investigation opens when a concern has more than one plausible explanation.</p>
        </EmptyState>
      </>
    );
  }

  const ordered = [...investigations].sort((a, b) => b.opened_at.localeCompare(a.opened_at));
  return (
    <div className={styles.surface} data-investigations>
      {status}
      {ordered.length > 1 ? (
        <nav className={styles.index} aria-label="Open questions">
          <p className={styles.indexTitle}>Questions on record</p>
          <ul className={styles.indexList}>
            {ordered.map((inv) => (
              <li key={inv.investigation_id}>
                <a href={`#${investigationAnchor(inv.investigation_id)}`} className={styles.indexLink}>
                  <span className={styles.indexPhase}>{PHASE_LABELS[inv.phase]}</span>
                  <span className={styles.indexQuestion}>{inv.question}</span>
                </a>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
      <ul className={styles.list}>
        {ordered.map((inv) => (
          <li key={inv.investigation_id}>
            <InvestigationDetail investigation={inv} headingLevel="h2" />
          </li>
        ))}
      </ul>
    </div>
  );
}
