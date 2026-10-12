"use client";

import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  getViewportForBounds,
  useReactFlow,
  useStoreApi,
  type EdgeTypes,
  type Node,
  type NodeTypes,
  type Rect,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { useEffect, useMemo, useRef } from "react";
import type {
  BeliefEdge as BeliefEdgeType,
  Bounds,
  Direction,
  Size,
  VariableNode as VariableNodeType,
} from "@/lib/causal-twin/graph";
import { BeliefEdge, SelectLinkContext } from "./BeliefEdge";
import { VariableNode } from "./VariableNode";
import styles from "./TwinCanvas.module.css";

// React Flow fits a view to its nodes only. An empty, inert node spanning
// the whole drawing makes every fit include the labels and bowed lines too.
const Extent = () => null;
const nodeTypes: NodeTypes = { variable: VariableNode, extent: Extent };

function extentNode(bounds: Bounds): Node {
  return {
    id: "twin-extent",
    type: "extent",
    position: { x: bounds.x, y: bounds.y },
    width: bounds.width,
    height: bounds.height,
    data: {},
    draggable: false,
    selectable: false,
    connectable: false,
    focusable: false,
    className: styles.extent,
    ariaRole: "presentation",
  };
}
const edgeTypes: EdgeTypes = { belief: BeliefEdge };
// Fit the whole map, but never so small that its words can't be read; a
// larger twin is then panned rather than shrunk.
const FIT = { padding: 0.08, minZoom: 0.5, maxZoom: 1.1 };

function reducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

type TwinCanvasProps = {
  nodes: VariableNodeType[];
  bounds: Bounds;
  edges: BeliefEdgeType[];
  direction: Direction;
  label: string;
  onSelect: (edgeId: string) => void;
  /** A link chosen outside the map (the list); the view moves to show it. */
  reveal: { edgeId: string } | null;
  /** The canvas's size, so the layout can suit its shape. */
  onResize: (size: Size) => void;
  /** False until the canvas is measured: the map is drawn once, in its final shape. */
  measured: boolean;
  /** A link is selected and drawn: everything else recedes. */
  focused?: boolean;
};

// Above the map rather than over it, so the controls never cover a link.
function Toolbar() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const duration = () => (reducedMotion() ? 0 : 200);
  return (
    <div className={styles.toolbar} role="toolbar" aria-label="Map view">
      <button
        type="button"
        className={styles.control}
        aria-label="Zoom in"
        title="Zoom in"
        onClick={() => zoomIn({ duration: duration() })}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path d="M8 3v10M3 8h10" />
        </svg>
      </button>
      <button
        type="button"
        className={styles.control}
        aria-label="Zoom out"
        title="Zoom out"
        onClick={() => zoomOut({ duration: duration() })}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path d="M3 8h10" />
        </svg>
      </button>
      <button
        type="button"
        className={styles.control}
        title="Fit the whole map in view"
        onClick={() => fitView({ ...FIT, duration: duration() * 2 })}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" />
        </svg>
        <span>Fit to view</span>
      </button>
    </div>
  );
}

function Reveal({ reveal, edges }: Pick<TwinCanvasProps, "reveal" | "edges">) {
  const { getNodesBounds, screenToFlowPosition, setViewport } = useReactFlow();
  const store = useStoreApi();
  useEffect(() => {
    const edge = reveal && edges.find((e) => e.id === reveal.edgeId);
    if (!edge) return;
    const { domNode, width, height } = store.getState();
    let bounds: Rect = getNodesBounds([edge.source, edge.target]);
    // The label too: it rides a bowed curve, and on a narrow map it can sit
    // well outside the two variables it joins.
    const label = domNode
      ?.querySelector(`button[data-edge-id="${edge.id}"]`)
      ?.getBoundingClientRect();
    if (label) {
      const a = screenToFlowPosition({ x: label.left, y: label.top });
      const b = screenToFlowPosition({ x: label.right, y: label.bottom });
      const x = Math.min(bounds.x, a.x);
      const y = Math.min(bounds.y, a.y);
      bounds = {
        x,
        y,
        width: Math.max(bounds.x + bounds.width, b.x) - x,
        height: Math.max(bounds.y + bounds.height, b.y) - y,
      };
    }
    void setViewport(getViewportForBounds(bounds, width, height, FIT.minZoom, FIT.maxZoom, 0.15), {
      duration: reducedMotion() ? 0 : 400,
    });
    // Only a new request moves the view, not a re-render.
  }, [reveal]);
  return null;
}

// The map itself. Pan by dragging; zoom with the toolbar, a pinch or
// ctrl + scroll. A plain scroll wheel scrolls the page, so the map never
// traps someone reading down the surface.
export function TwinCanvas({
  nodes,
  bounds,
  edges,
  direction,
  label,
  onSelect,
  reveal,
  onResize,
  measured,
  focused = false,
}: TwinCanvasProps) {
  const canvas = useRef<HTMLDivElement>(null);
  const drawn = useMemo(() => [extentNode(bounds), ...nodes], [bounds, nodes]);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) =>
      onResize({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    observer.observe(canvas.current!);
    return () => observer.disconnect();
  }, [onResize]);

  return (
    <ReactFlowProvider>
      <div className={styles.frame}>
        <Toolbar />
        <div
          ref={canvas}
          className={styles.canvas}
          role="group"
          aria-label={label}
          data-direction={direction}
          data-focus={focused || undefined}
        >
          {measured ? (
            <SelectLinkContext.Provider value={onSelect}>
              <ReactFlow
                // A new direction is a new layout: start it fitted.
                key={direction}
                nodes={drawn}
                edges={edges}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                fitView
                fitViewOptions={FIT}
                minZoom={0.25}
                maxZoom={2}
                nodesDraggable={false}
                nodesConnectable={false}
                nodesFocusable={false}
                edgesFocusable={false}
                elementsSelectable={false}
                zoomOnScroll={false}
                panOnScroll={false}
                preventScrolling={false}
                zoomOnDoubleClick={false}
              >
                <Background variant={BackgroundVariant.Dots} gap={24} size={1.4} color="var(--grid-dot)" />
                <Reveal reveal={reveal} edges={edges} />
              </ReactFlow>
            </SelectLinkContext.Provider>
          ) : null}
        </div>
      </div>
    </ReactFlowProvider>
  );
}
