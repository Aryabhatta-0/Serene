"use client";

import { useCallback, useId, useMemo, useState, type ReactNode } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { LineKey, type LineKeyEntry } from "@/components/notation/LineKey";
import { LineMark } from "@/components/notation/LineMark";
import { CATEGORIES, CATEGORY_ORDER } from "@/lib/causal-twin/categories";
import { buildTwinGraph, chooseDirection, type Size } from "@/lib/causal-twin/graph";
import type { CausalEdge, CausalTwin } from "@/lib/causal-twin/model";
import type { TwinSource } from "@/lib/causal-twin/source";
import { LinkList } from "./LinkList";
import { SelectedLink } from "./SelectedLink";
import { TwinCanvas } from "./TwinCanvas";
import styles from "./CausalTwin.module.css";

const LINK_KEY: readonly LineKeyEntry[] = CATEGORY_ORDER.map((category) => ({
  certainty: CATEGORIES[category].certainty,
  term: CATEGORIES[category].term,
  description: CATEGORIES[category].description,
}));

export type CausalTwinViewProps = {
  source: TwinSource;
  /** Controlled selection; omit to let the view keep its own. */
  selectedEdgeId?: string | null;
  onSelectedEdgeChange?: (edgeId: string | null) => void;
  /** Extra detail for the selected link (the provenance panel, #39). */
  renderEdgeDetail?: (edge: CausalEdge) => ReactNode;
  onRetry?: () => void;
};

// The Causal Twin surface: what Serene currently believes may influence what,
// how firmly each link is held, and what has been refuted. It draws only the
// twin it is given and says plainly when there is none.
export function CausalTwinView({ source, ...selection }: CausalTwinViewProps) {
  switch (source.status) {
    case "unconnected":
      return (
        <>
          <EmptyState title="No links to draw yet">
            <p>
              The map is built only from recorded evidence. Until there is some, it stays empty
              rather than guessing.
            </p>
          </EmptyState>
          <LineKey title="How links will be drawn" entries={LINK_KEY} />
        </>
      );
    case "loading":
      return (
        <div className={styles.loading} role="status">
          <span className="visually-hidden">Loading the Causal Twin</span>
          <LineMark certainty="unknown" className={styles.loadingLine} />
          <LineMark certainty="unknown" className={styles.loadingLine} />
        </div>
      );
    case "error":
      return (
        <EmptyState title="The map couldn’t be drawn">
          <p>
            What Serene sent did not pass its own checks, so nothing is drawn rather than drawing
            something wrong. Nothing in your family’s record was changed.
          </p>
          {selection.onRetry ? (
            <p>
              <button type="button" className="button" onClick={selection.onRetry}>
                Try again
              </button>
            </p>
          ) : null}
        </EmptyState>
      );
    case "ready":
      if (source.twin.edges.length === 0) {
        return (
          <>
            <EmptyState title="No links recorded yet">
              <p>
                Serene has not formed any links about your child yet. Each one appears here once
                there is recorded evidence for it to rest on.
              </p>
            </EmptyState>
            <LineKey title="How links will be drawn" entries={LINK_KEY} />
          </>
        );
      }
      return <TwinMap twin={source.twin} {...selection} />;
  }
}

type TwinMapProps = Omit<CausalTwinViewProps, "source" | "onRetry"> & { twin: CausalTwin };

function TwinMap({ twin, selectedEdgeId, onSelectedEdgeChange, renderEdgeDetail }: TwinMapProps) {
  const headingId = useId();
  // The map waits for the canvas to be measured, so it is laid out once, in
  // the direction that suits it. (The list below carries every link anyway.)
  const [size, setSize] = useState<Size | null>(null);
  const direction = useMemo(() => (size ? chooseDirection(twin, size) : "LR"), [twin, size]);
  const [ownSelection, setOwnSelection] = useState<string | null>(null);
  const [reveal, setReveal] = useState<{ edgeId: string } | null>(null);
  const selectedId = selectedEdgeId !== undefined ? selectedEdgeId : ownSelection;

  const select = useCallback(
    (edgeId: string | null) => {
      setOwnSelection(edgeId);
      onSelectedEdgeChange?.(edgeId);
    },
    [onSelectedEdgeChange],
  );
  // Link buttons are toggles (aria-pressed): choosing the selected link again
  // clears it.
  const toggle = useCallback(
    (edgeId: string) => select(edgeId === selectedId ? null : edgeId),
    [select, selectedId],
  );

  const graph = useMemo(() => buildTwinGraph(twin, direction, selectedId), [twin, direction, selectedId]);
  const selected = twin.edges.find((e) => e.edge_id === selectedId) ?? null;
  const total = twin.edges.length;

  return (
    <section className={styles.twin} aria-labelledby={headingId}>
      <header className={styles.intro}>
        <h2 id={headingId} className={styles.heading}>
          What Serene believes now
        </h2>
        <p>
          {total === 1 ? "One link is" : `${total} links are`} on record. Each line joins two
          parts of your child’s days, drawn by how firmly Serene holds it. Refuted links stay on
          the map, struck through.
        </p>
      </header>

      <ul className={styles.legend} aria-label="How links are drawn">
        {CATEGORY_ORDER.map((category) => (
          <li key={category} className={styles.legendItem} data-category={category}>
            <LineMark certainty={CATEGORIES[category].certainty} className={styles.legendMark} />
            <span className={styles.legendTerm}>{CATEGORIES[category].term}</span>
            <span className={styles.legendCount}>
              {graph.counts[category]}
              <span className="visually-hidden">{graph.counts[category] === 1 ? " link" : " links"}</span>
            </span>
          </li>
        ))}
      </ul>

      <div className={styles.stage}>
        {graph.edges.length > 0 ? (
          <TwinCanvas
            nodes={graph.nodes}
            bounds={graph.bounds}
            edges={graph.edges}
            direction={direction}
            label="Map of links. Drag to move around; use the buttons to zoom."
            onSelect={toggle}
            reveal={reveal}
            onResize={setSize}
            measured={size !== null}
          />
        ) : (
          <p className={styles.unplacedOnly}>
            None of these links can be placed on the map yet, because what they connect has not
            been named. They are listed below.
          </p>
        )}
        <SelectedLink edge={selected} onClear={() => select(null)}>
          {selected && renderEdgeDetail ? renderEdgeDetail(selected) : null}
        </SelectedLink>
      </div>

      <LinkList
        edges={twin.edges}
        selectedEdgeId={selectedId}
        onSelect={(edgeId) => {
          toggle(edgeId);
          if (edgeId !== selectedId) setReveal({ edgeId });
        }}
      />

      <LineKey title="How to read the map" entries={LINK_KEY} />
    </section>
  );
}
