import { useId } from "react";
import { LineMark } from "@/components/notation/LineMark";
import { CATEGORIES, CATEGORY_ORDER, categorize, isContested, variableLabel } from "@/lib/causal-twin/categories";
import { isPlaced } from "@/lib/causal-twin/graph";
import type { CausalEdge } from "@/lib/causal-twin/model";
import styles from "./CausalTwin.module.css";

type LinkListProps = {
  edges: readonly CausalEdge[];
  selectedEdgeId: string | null;
  onSelect: (edgeId: string) => void;
};

// Every link in the twin as text, grouped by how firmly it is held. It is the
// map's reading order, the way in for keyboard and screen-reader users, and
// the only place a link with unnamed variables can appear.
export function LinkList({ edges, selectedEdgeId, onSelect }: LinkListProps) {
  const headingId = useId();
  const groups = CATEGORY_ORDER.map((category) => ({
    category,
    edges: edges.filter((e) => categorize(e) === category),
  })).filter((g) => g.edges.length > 0);

  return (
    <section className={styles.list} aria-labelledby={headingId}>
      <h3 id={headingId} className={styles.listTitle}>
        Every link, by how firmly it is held
      </h3>
      {groups.map(({ category, edges: group }) => (
        <div key={category} className={styles.group} data-category={category}>
          <h4 className={styles.groupTitle}>
            <LineMark certainty={CATEGORIES[category].certainty} className={styles.groupMark} />
            {CATEGORIES[category].term}
          </h4>
          <ul className={styles.items}>
            {group.map((edge) => (
              <li key={edge.edge_id}>
                <button
                  type="button"
                  className={styles.item}
                  aria-pressed={edge.edge_id === selectedEdgeId}
                  data-edge-id={edge.edge_id}
                  onClick={() => onSelect(edge.edge_id)}
                >
                  <span className={styles.itemStatement}>{edge.relationship}</span>
                  <span className={styles.itemMeta}>
                    {isPlaced(edge)
                      ? `${variableLabel(edge.cause)} to ${variableLabel(edge.effect)}`
                      : "Not on the map yet: what it connects has not been named"}
                    {isContested(edge) ? ". Some evidence points the other way" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
