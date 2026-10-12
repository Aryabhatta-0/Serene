import { useId, type ReactNode } from "react";
import { LineMark } from "@/components/notation/LineMark";
import {
  CATEGORIES,
  LEARNING_NOTES,
  categorize,
  isContested,
  variableLabel,
} from "@/lib/causal-twin/categories";
import type { CausalEdge } from "@/lib/causal-twin/model";
import styles from "./CausalTwin.module.css";

// The questions the provenance panel answers, in its order, for jumping
// straight to one inside a long explanation.
const JUMPS: readonly (readonly [string, string])[] = [
  ["verdict", "Why"],
  ["support", "For"],
  ["against", "Against"],
  ["experiments", "Experiments"],
  ["scope", "Where and when"],
  ["alternatives", "Alternatives"],
  ["supersession", "Replaced"],
  ["lineage", "Trail to evidence"],
];

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

type SelectedLinkProps = {
  edge: CausalEdge | null;
  onClear: () => void;
  /** Where a fuller account of the link attaches (the provenance panel, #39). */
  children?: ReactNode;
};

// The link the parent has chosen, read in plain words. It summarises what the
// twin records about the link; the full evidence trail is the provenance
// panel's job. Every figure is a count of recorded items, never a score.
export function SelectedLink({ edge, onClear, children }: SelectedLinkProps) {
  const headingId = useId();
  if (!edge) {
    return (
      <aside className={styles.selection} aria-labelledby={headingId}>
        <h3 id={headingId} className={styles.selectionTitle}>
          Selected link
        </h3>
        <p className={styles.selectionLead}>Why does Serene believe this?</p>
        <p className={styles.selectionHint}>
          Choose a link on the map or in the list below to see what supports it, what counts
          against it, and the trail down to raw evidence.
        </p>
      </aside>
    );
  }

  const category = categorize(edge);
  const meta = CATEGORIES[category];
  const observed = edge.support.filter((s) => s.kind === "OBSERVATIONAL").length;
  const tested = edge.support.length - observed;
  const learningNote = edge.learning_status && LEARNING_NOTES[edge.learning_status];

  return (
    <aside
      className={styles.selection}
      aria-labelledby={headingId}
      data-selected-edge-id={edge.edge_id}
      data-category={category}
      // Escape from anywhere in the panel closes it, like the Clear button.
      onKeyDown={(event) => {
        if (event.key === "Escape") onClear();
      }}
    >
      <div className={styles.selectionHead}>
        <h3 id={headingId} className={styles.selectionTitle}>
          Selected link
        </h3>
        <button type="button" className={styles.clear} onClick={onClear}>
          Clear
        </button>
      </div>
      <p className={styles.selectionState}>
        <LineMark certainty={meta.certainty} className={styles.selectionMark} />
        {meta.term}
      </p>
      <p className={styles.selectionStatement}>{edge.relationship}</p>
      {edge.cause !== null && edge.effect !== null ? (
        <p className={styles.ends} aria-hidden="true">
          <span>{variableLabel(edge.cause)}</span>
          <LineMark certainty={meta.certainty} className={styles.endsMark} />
          <span>{variableLabel(edge.effect)}</span>
        </p>
      ) : null}
      <p className={styles.selectionNote}>{meta.description}</p>

      <dl className={styles.facts}>
        <div>
          <dt>Connects</dt>
          <dd>
            {edge.cause !== null && edge.effect !== null
              ? `${variableLabel(edge.cause)} to ${variableLabel(edge.effect)}`
              : "Not placed on the map yet: what it connects has not been named."}
          </dd>
        </div>
        <div>
          <dt>What supports it</dt>
          <dd>
            {edge.support.length === 0
              ? "Nothing recorded yet."
              : [
                  observed > 0 ? plural(observed, "recorded observation", "recorded observations") : null,
                  tested > 0
                    ? plural(tested, "supporting experiment outcome", "supporting experiment outcomes")
                    : null,
                ]
                  .filter(Boolean)
                  .join(" and ") + "."}
          </dd>
        </div>
        <div>
          <dt>What counts against it</dt>
          <dd>
            {edge.counterevidence.length === 0
              ? "Nothing recorded."
              : `${plural(edge.counterevidence.length, "recorded item", "recorded items")}${
                  edge.contradicting_outcomes.length > 0
                    ? `, including ${plural(
                        edge.contradicting_outcomes.length,
                        "experiment outcome that contradicts it",
                        "experiment outcomes that contradict it",
                      )}`
                    : ""
                }.`}
          </dd>
        </div>
        <div>
          <dt>Holds in</dt>
          <dd>{edge.scope.contexts.map(variableLabel).join(", ")}</dd>
        </div>
      </dl>

      {isContested(edge) ? (
        <p className={styles.caution}>Some recorded evidence points the other way.</p>
      ) : null}
      {learningNote ? <p className={styles.caution}>{learningNote}</p> : null}

      {children ? (
        <>
          <nav className={styles.jump} aria-label="Parts of this explanation">
            {JUMPS.map(([name, label]) => (
              <a key={name} href={`#provenance-${name}`}>
                {label}
              </a>
            ))}
          </nav>
          {children}
        </>
      ) : null}

      <p className={styles.reference}>
        <span>Link reference</span> <code>{edge.edge_id}</code>
      </p>
    </aside>
  );
}
