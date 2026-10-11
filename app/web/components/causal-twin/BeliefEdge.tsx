"use client";

import { EdgeLabelRenderer, type EdgeProps } from "@xyflow/react";
import { createContext, useContext } from "react";
import { LineMark } from "@/components/notation/LineMark";
import { CATEGORIES, variableLabel, type EdgeCategory } from "@/lib/causal-twin/categories";
import { curvePoint, type BeliefEdge as BeliefEdgeType } from "@/lib/causal-twin/graph";
import styles from "./TwinCanvas.module.css";

type Stroke = {
  color: string;
  width: number;
  dasharray?: string;
  /** Refuted: cross-ticks over the line, as in the LineMark notation. */
  strike?: boolean;
  /** Replaced: drawn hollow, an outline with its core cut out. */
  hollow?: boolean;
};

// The certainty notation at map scale. Each category differs in line style,
// not only in colour, and its name is always written on the label.
export const EDGE_STROKES: Record<EdgeCategory, Stroke> = {
  tested: { color: "var(--ink)", width: 2.5 },
  observed: { color: "var(--ink)", width: 2, dasharray: "8 6" },
  hypothesis: { color: "var(--ink-muted)", width: 3, dasharray: "0.1 7" },
  refuted: { color: "var(--ink-faint)", width: 2, strike: true },
  superseded: { color: "var(--ink-faint)", width: 6, hollow: true },
};

export const SelectLinkContext = createContext<(edgeId: string) => void>(() => {});

// A quadratic curve whose control point is moved off the straight line by
// `bow` (chosen by the layout so labels never collide); the label sits at `t`.
function bowedPath(sx: number, sy: number, tx: number, ty: number, bow: { x: number; y: number }, t: number) {
  const control = { x: (sx + tx) / 2 + bow.x, y: (sy + ty) / 2 + bow.y };
  const label = curvePoint({ x: sx, y: sy }, control, { x: tx, y: ty }, t);
  return {
    path: `M ${sx},${sy} Q ${control.x},${control.y} ${tx},${ty}`,
    labelX: label.x,
    labelY: label.y,
  };
}

export function BeliefEdge({ id, sourceX, sourceY, targetX, targetY, data }: EdgeProps<BeliefEdgeType>) {
  const select = useContext(SelectLinkContext);
  if (!data) return null;
  const { edge, category, contested, bow, labelAt, selected } = data;
  const stroke = EDGE_STROKES[category];
  const meta = CATEGORIES[category];
  const { path, labelX, labelY } = bowedPath(sourceX, sourceY, targetX, targetY, bow, labelAt);
  const markerId = `twin-arrow-${id}`;
  const width = stroke.width + (selected ? 1.5 : 0);

  return (
    <>
      <defs>
        <marker
          id={markerId}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="11"
          markerHeight="11"
          markerUnits="userSpaceOnUse"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill={stroke.color} />
        </marker>
      </defs>
      <g
        className={styles.edge}
        data-edge-id={edge.edge_id}
        data-category={category}
        data-selected={selected || undefined}
      >
        {selected ? <path d={path} className={styles.halo} /> : null}
        <path
          d={path}
          className={styles.stroke}
          data-stroke
          fill="none"
          stroke={stroke.color}
          strokeWidth={width}
          strokeDasharray={stroke.dasharray}
          strokeLinecap={stroke.dasharray ? "round" : "butt"}
          markerEnd={`url(#${markerId})`}
        />
        {stroke.strike ? (
          <path
            d={path}
            fill="none"
            stroke={stroke.color}
            strokeWidth={12}
            strokeDasharray="1.5 14"
            data-strike
          />
        ) : null}
        {stroke.hollow ? (
          <path d={path} fill="none" className={styles.hollowCore} strokeWidth={width - 3.5} data-hollow />
        ) : null}
        {/* A wide invisible band, so the line is easy to click or tap. */}
        <path
          d={path}
          fill="none"
          stroke="transparent"
          strokeWidth={24}
          className={styles.hit}
          onClick={() => select(edge.edge_id)}
        />
      </g>
      <EdgeLabelRenderer>
        <button
          type="button"
          className={`${styles.label} nodrag nopan`}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          data-category={category}
          data-edge-id={edge.edge_id}
          aria-pressed={selected}
          onClick={() => select(edge.edge_id)}
        >
          <span className={styles.labelHead}>
            <LineMark certainty={meta.certainty} className={styles.labelMark} />
            <span className={styles.labelTerm}>{meta.term}</span>
          </span>
          <span className={styles.labelText}>{edge.relationship}</span>
          {contested ? <span className={styles.labelFlag}>Evidence against it too</span> : null}
          <span className="visually-hidden">
            {`, from ${variableLabel(edge.cause!)} to ${variableLabel(edge.effect!)}`}
          </span>
        </button>
      </EdgeLabelRenderer>
    </>
  );
}
