"use client";

import { useCallback, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { LineKey, type LineKeyEntry } from "@/components/notation/LineKey";
import { LineMark } from "@/components/notation/LineMark";
import { CATEGORIES, CATEGORY_ORDER, categorize, type EdgeCategory } from "@/lib/causal-twin/categories";
import { buildTwinGraph, chooseDirection, isPlaced, type Size } from "@/lib/causal-twin/graph";
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

export type EdgeDetailActions = { selectEdge: (edgeId: string) => void };

export type CausalTwinViewProps = {
  source: TwinSource;
  /** Controlled selection; omit to let the view keep its own. */
  selectedEdgeId?: string | null;
  onSelectedEdgeChange?: (edgeId: string | null) => void;
  /**
   * Extra detail for the selected link (the provenance panel, #39).
   * `selectEdge` chooses another link and moves the map to show it.
   */
  renderEdgeDetail?: (edge: CausalEdge, actions: EdgeDetailActions) => ReactNode;
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
        <EmptyState title="The map couldn’t be drawn" tone="stopped">
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
  // Kinds of link the parent has set aside to see the rest more clearly. The
  // list below always carries every link; only the map is filtered.
  const [hidden, setHidden] = useState<ReadonlySet<EdgeCategory>>(() => new Set());
  const drawnTwin = useMemo(
    () => (hidden.size === 0 ? twin : { ...twin, edges: twin.edges.filter((e) => !hidden.has(categorize(e))) }),
    [twin, hidden],
  );
  // The map waits for the canvas to be measured, so it is laid out once, in
  // the direction that suits it. (The list below carries every link anyway.)
  const [size, setSize] = useState<Size | null>(null);
  const direction = useMemo(() => (size ? chooseDirection(drawnTwin, size) : "LR"), [drawnTwin, size]);
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
  // Chosen outside the map (the list, the panel): the map moves to show it.
  // A link of a kind that was set aside is put back on the map first.
  const choose = useCallback(
    (edgeId: string) => {
      const edge = twin.edges.find((e) => e.edge_id === edgeId);
      if (edge && hidden.has(categorize(edge))) {
        setHidden((h) => {
          const next = new Set(h);
          next.delete(categorize(edge));
          return next;
        });
      }
      select(edgeId);
      setReveal({ edgeId });
    },
    [select, twin, hidden],
  );
  // Closing the panel hands focus back to the link in the list, which is
  // always there (a link may not be drawn), without scrolling the page.
  const list = useRef<HTMLDivElement>(null);
  const clear = useCallback(() => {
    const closed = selectedId;
    select(null);
    list.current?.querySelector<HTMLElement>(`button[data-edge-id="${closed}"]`)?.focus({ preventScroll: true });
  }, [select, selectedId]);

  const graph = useMemo(() => buildTwinGraph(drawnTwin, direction, selectedId), [drawnTwin, direction, selectedId]);
  const selected = twin.edges.find((e) => e.edge_id === selectedId) ?? null;
  const drawnSelection = graph.edges.find((e) => e.id === selectedId) ?? null;
  // With a link selected, its two ends stay in full; everything else recedes.
  const nodes = useMemo(() => {
    if (!drawnSelection?.data) return graph.nodes;
    const ends = new Set([drawnSelection.data.edge.cause, drawnSelection.data.edge.effect]);
    return graph.nodes.map((n) => ({
      ...n,
      data: { ...n.data, focus: ends.has(n.data.tag) ? ("related" as const) : ("dim" as const) },
    }));
  }, [graph.nodes, drawnSelection]);
  const counts = useMemo(() => {
    const out = Object.fromEntries(CATEGORY_ORDER.map((c) => [c, 0])) as Record<EdgeCategory, number>;
    for (const edge of twin.edges) out[categorize(edge)] += 1;
    return out;
  }, [twin]);
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
          the map, struck through. Choose any link to see why Serene holds it.
        </p>
      </header>

      <div className={styles.mapBar}>
        <p className={styles.filtersLabel} id={`${headingId}-legend`}>
          Links on the map
        </p>
        <ul className={styles.legend} aria-label="How links are drawn">
          {CATEGORY_ORDER.map((category) => (
            <li key={category} className={styles.legendItem} data-category={category} data-empty={counts[category] === 0 || undefined}>
              <label className={styles.filter}>
                {/* Each kind of link can be set aside on the map; the list keeps every one. */}
                <input
                  type="checkbox"
                  checked={counts[category] > 0 && !hidden.has(category)}
                  disabled={counts[category] === 0}
                  aria-describedby={`${headingId}-legend`}
                  onChange={(event) => {
                    const show = event.currentTarget.checked;
                    setHidden((h) => {
                      const next = new Set(h);
                      if (show) next.delete(category);
                      else next.add(category);
                      return next;
                    });
                  }}
                />
                <LineMark certainty={CATEGORIES[category].certainty} className={styles.legendMark} />
                <span className={styles.legendTerm}>{CATEGORIES[category].term}</span>
                <span className={styles.legendCount}>
                  {counts[category]}
                  <span className="visually-hidden">{counts[category] === 1 ? " link" : " links"}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </div>

      <div className={styles.stage} data-has-selection={selected ? "" : undefined}>
        <div className={styles.mapColumn}>
          {graph.edges.length > 0 ? (
            <TwinCanvas
              nodes={nodes}
              bounds={graph.bounds}
              edges={graph.edges}
              direction={direction}
              label="Map of links. Drag to move around; use the buttons to zoom."
              onSelect={toggle}
              reveal={reveal}
              onResize={setSize}
              measured={size !== null}
              focused={drawnSelection !== null}
            />
          ) : (
            <p className={styles.unplacedOnly}>
              {hidden.size > 0 && twin.edges.some(isPlaced)
                ? "Every kind of link on the map is set aside. Turn one back on above, or choose a link from the list below."
                : "None of these links can be placed on the map yet, because what they connect has not been named. They are listed below."}
            </p>
          )}
        </div>
        <SelectedLink edge={selected} onClear={clear}>
          {selected && renderEdgeDetail ? renderEdgeDetail(selected, { selectEdge: choose }) : null}
        </SelectedLink>
      </div>

      <div ref={list} className={styles.listWrap}>
        <LinkList
          edges={twin.edges}
          selectedEdgeId={selectedId}
          onSelect={(edgeId) => (edgeId === selectedId ? select(null) : choose(edgeId))}
        />
        <LineKey title="How to read the map" entries={LINK_KEY} />
      </div>
    </section>
  );
}
