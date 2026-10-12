import { Position, type Edge, type Node, type NodeHandle } from "@xyflow/react";
import { categorize, isContested, variableLabel, type EdgeCategory, CATEGORY_ORDER } from "./categories";
import type { CausalEdge, CausalTwin } from "./model";

// Turns a Causal Twin into a React Flow graph. Everything drawn comes from the
// twin: one node per named variable, one edge per hypothesis, positions from a
// deterministic layered layout. Nothing is added, merged or dropped: an edge
// whose variables are not named yet is returned in `unplaced` rather than
// being drawn between guessed endpoints.

export type Direction = "LR" | "TB";

export const NODE_WIDTH = 184;
export const NODE_HEIGHT = 64;

const GAPS: Record<Direction, { rank: number; row: number }> = {
  // Wide: causes on the left, effects to the right, labels in between.
  LR: { rank: 216, row: 88 },
  // Narrow: causes above, effects below.
  TB: { rank: 152, row: 72 },
};

// Room a link's label takes on the map (centre-based, with a margin), and the
// places it may be tried, nearest first. Wide maps stack labels beside each
// other by bowing their lines; narrow ones mostly slide labels along the line
// (`t`: 0 at the cause, 1 at the effect).
const LABEL_BOX: Record<Direction, { w: number; h: number }> = {
  LR: { w: 184, h: 84 },
  TB: { w: 196, h: 44 },
};
const LABEL_SPOTS: Record<Direction, Array<{ bow: number; t: number }>> = {
  LR: [0, 1, -1, 2, -2, 3, -3, 4, -4].map((k) => ({ bow: k * LABEL_BOX.LR.h, t: 0.5 })),
  TB: [0, 56, -56, 112, -112, 200, -200, 300, -300].flatMap((bow) =>
    [0.5, 0.3, 0.7].map((t) => ({ bow, t })),
  ),
};

export type VariableNodeData = {
  tag: string;
  label: string;
  direction: Direction;
  /** With a link selected: whether this variable is one of its two ends. */
  focus?: "related" | "dim";
};

export type BeliefEdgeData = {
  edge: CausalEdge;
  category: EdgeCategory;
  contested: boolean;
  /** How far the curve's control point sits off the straight line, in px. */
  bow: { x: number; y: number };
  /** Where along the line the label sits, from 0 (cause) to 1 (effect). */
  labelAt: number;
  selected: boolean;
};

export type VariableNode = Node<VariableNodeData, "variable">;
export type BeliefEdge = Edge<BeliefEdgeData, "belief">;

export type Bounds = { x: number; y: number; width: number; height: number };

export type TwinGraph = {
  nodes: VariableNode[];
  /** Everything drawn, labels and bowed lines included, so a fit shows it all. */
  bounds: Bounds;
  edges: BeliefEdge[];
  /** Edges with no named cause or effect: listed, never drawn. */
  unplaced: CausalEdge[];
  counts: Record<EdgeCategory, number>;
};

type PlacedEdge = CausalEdge & { cause: string; effect: string };

export function isPlaced(edge: CausalEdge): edge is PlacedEdge {
  return edge.cause !== null && edge.effect !== null && edge.cause !== edge.effect;
}

function handlesFor(direction: Direction): NodeHandle[] {
  // Declared up front so the graph lays out (and renders on the server)
  // before the browser has measured anything.
  const [source, target] =
    direction === "LR"
      ? [
          { position: Position.Right, x: NODE_WIDTH - 1, y: NODE_HEIGHT / 2 - 0.5 },
          { position: Position.Left, x: 0, y: NODE_HEIGHT / 2 - 0.5 },
        ]
      : [
          { position: Position.Bottom, x: NODE_WIDTH / 2 - 0.5, y: NODE_HEIGHT - 1 },
          { position: Position.Top, x: NODE_WIDTH / 2 - 0.5, y: 0 },
        ];
  return [
    { type: "source", width: 1, height: 1, ...source },
    { type: "target", width: 1, height: 1, ...target },
  ];
}

// Longest-path layering. Cycles are possible (two rival hypotheses can point
// in opposite directions), so edges that close a cycle are ignored for
// ranking only; they are still drawn.
function rankVariables(variables: string[], links: Array<[string, string]>): Map<string, number> {
  const out = new Map(variables.map((v) => [v, [] as string[]]));
  for (const [cause, effect] of links) out.get(cause)!.push(effect);
  for (const targets of out.values()) targets.sort();

  const forward: Array<[string, string]> = [];
  const state = new Map<string, "open" | "done">();
  const visit = (v: string) => {
    state.set(v, "open");
    for (const w of out.get(v)!) {
      if (state.get(w) === "open") continue; // closes a cycle
      forward.push([v, w]);
      if (!state.has(w)) visit(w);
    }
    state.set(v, "done");
  };
  for (const v of variables) if (!state.has(v)) visit(v);

  const preds = new Map(variables.map((v) => [v, [] as string[]]));
  for (const [cause, effect] of forward) preds.get(effect)!.push(cause);
  const rank = new Map<string, number>();
  const rankOf = (v: string): number => {
    const known = rank.get(v);
    if (known !== undefined) return known;
    const r = Math.max(-1, ...preds.get(v)!.map(rankOf)) + 1;
    rank.set(v, r);
    return r;
  };
  for (const v of variables) rankOf(v);
  return rank;
}

export function buildTwinGraph(
  twin: CausalTwin,
  direction: Direction = "LR",
  selectedEdgeId: string | null = null,
): TwinGraph {
  const placed = twin.edges.filter(isPlaced);
  const unplaced = twin.edges.filter((e) => !isPlaced(e));

  const variables = [...new Set(placed.flatMap((e) => [e.cause, e.effect]))].sort();
  const rank = rankVariables(
    variables,
    placed.map((e) => [e.cause, e.effect]),
  );

  // Order each layer by where its causes sit, so lines cross as little as a
  // single deterministic pass allows; ties fall back to the variable name.
  const layers: string[][] = [];
  for (const v of variables) (layers[rank.get(v)!] ??= []).push(v);
  const slot = new Map<string, number>();
  for (const layer of layers) {
    const weight = (v: string) => {
      const causes = placed.filter((e) => e.effect === v && slot.has(e.cause));
      return causes.length === 0
        ? Number.POSITIVE_INFINITY
        : causes.reduce((sum, e) => sum + slot.get(e.cause)!, 0) / causes.length;
    };
    const weights = new Map(layer.map((v) => [v, weight(v)]));
    layer.sort((a, b) => weights.get(a)! - weights.get(b)! || (a < b ? -1 : 1));
    layer.forEach((v, i) => slot.set(v, i));
  }

  const gap = GAPS[direction];
  const handles = handlesFor(direction);
  const nodes: VariableNode[] = layers.flatMap((layer, r) =>
    layer.map((tag, i) => {
      const along = r * ((direction === "LR" ? NODE_WIDTH : NODE_HEIGHT) + gap.rank);
      const across =
        (i - (layer.length - 1) / 2) * ((direction === "LR" ? NODE_HEIGHT : NODE_WIDTH) + gap.row);
      return {
        id: tag,
        type: "variable" as const,
        position: direction === "LR" ? { x: along, y: across } : { x: across, y: along },
        data: { tag, label: variableLabel(tag), direction },
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        handles,
        draggable: false,
        connectable: false,
        selectable: false,
      };
    }),
  );

  const spots = placeLabels(placed, nodes, direction);

  const edges: BeliefEdge[] = placed.map((edge) => {
    const category = categorize(edge);
    return {
      id: edge.edge_id,
      type: "belief" as const,
      source: edge.cause,
      target: edge.effect,
      data: {
        edge,
        category,
        contested: isContested(edge),
        ...spots.byEdge.get(edge.edge_id)!,
        selected: edge.edge_id === selectedEdgeId,
      },
      // The selected link draws above the others.
      zIndex: edge.edge_id === selectedEdgeId ? 1 : 0,
      selectable: false,
      focusable: false,
    };
  });

  const counts = Object.fromEntries(CATEGORY_ORDER.map((c) => [c, 0])) as Record<EdgeCategory, number>;
  for (const edge of twin.edges) counts[categorize(edge)] += 1;

  return { nodes, bounds: spots.bounds, edges, unplaced, counts };
}

type Box = { x: number; y: number; w: number; h: number };

const overlaps = (a: Box, b: Box) =>
  Math.abs(a.x - b.x) * 2 < a.w + b.w && Math.abs(a.y - b.y) * 2 < a.h + b.h;

/** A point on the quadratic from `s` to `e` whose control is `c`. */
export function curvePoint(
  s: { x: number; y: number },
  c: { x: number; y: number },
  e: { x: number; y: number },
  t: number,
) {
  const at = (a: number, m: number, b: number) => (1 - t) ** 2 * a + 2 * (1 - t) * t * m + t ** 2 * b;
  return { x: at(s.x, c.x, e.x), y: at(s.y, c.y, e.y) };
}

/** Where a link leaves its cause and meets its effect, from the declared handles. */
function endpoints(edge: PlacedEdge, byId: Map<string, VariableNode>, direction: Direction) {
  const from = byId.get(edge.cause)!.position;
  const to = byId.get(edge.effect)!.position;
  return direction === "LR"
    ? { s: { x: from.x + NODE_WIDTH, y: from.y + NODE_HEIGHT / 2 }, e: { x: to.x, y: to.y + NODE_HEIGHT / 2 } }
    : { s: { x: from.x + NODE_WIDTH / 2, y: from.y + NODE_HEIGHT }, e: { x: to.x + NODE_WIDTH / 2, y: to.y } };
}

// Places every label so that none covers another label or a variable. Firmer
// links are placed first and get the plainest spot (a straight line, label at
// its middle). A curve is bowed so it passes through its label, and two links
// between the same variables never share a curve. Deterministic: the same
// twin always gets the same map.
function placeLabels(placed: PlacedEdge[], nodes: VariableNode[], direction: Direction) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const size = LABEL_BOX[direction];
  const taken: Box[] = nodes.map((n) => ({
    x: n.position.x + NODE_WIDTH / 2,
    y: n.position.y + NODE_HEIGHT / 2,
    w: NODE_WIDTH + 8,
    h: NODE_HEIGHT + 8,
  }));
  const bowsByPair = new Map<string, Set<number>>();
  const order = [...placed].sort(
    (a, b) =>
      CATEGORY_ORDER.indexOf(categorize(a)) - CATEGORY_ORDER.indexOf(categorize(b)) ||
      (a.edge_id < b.edge_id ? -1 : 1),
  );

  const placedSpots = new Map<string, { bow: { x: number; y: number }; labelAt: number }>();
  for (const edge of order) {
    const { s, e } = endpoints(edge, byId, direction);
    const pair = [edge.cause, edge.effect].sort().join("|");
    const usedBows = bowsByPair.get(pair) ?? new Set<number>();
    const candidates = LABEL_SPOTS[direction].filter(({ bow }) => !usedBows.has(bow));
    const fits = (spot: { bow: number; t: number }) => {
      const box = { ...labelCentre(s, e, spot, direction), ...size };
      return taken.every((other) => !overlaps(box, other));
    };
    const spot = candidates.find(fits) ?? candidates[0] ?? { bow: 0, t: 0.5 };
    taken.push({ ...labelCentre(s, e, spot, direction), ...size });
    bowsByPair.set(pair, usedBows.add(spot.bow));
    placedSpots.set(edge.edge_id, { bow: controlShift(spot.bow, direction), labelAt: spot.t });
  }
  if (taken.length === 0) return { byEdge: placedSpots, bounds: { x: 0, y: 0, width: 0, height: 0 } };
  const left = Math.min(...taken.map((b) => b.x - b.w / 2));
  const top = Math.min(...taken.map((b) => b.y - b.h / 2));
  const bounds = {
    x: left,
    y: top,
    width: Math.max(...taken.map((b) => b.x + b.w / 2)) - left,
    height: Math.max(...taken.map((b) => b.y + b.h / 2)) - top,
  };
  return { byEdge: placedSpots, bounds };
}

// A bow moves the line's middle sideways (across the direction of reading).
// The curve's midpoint lies halfway to its control point, so the control
// point moves twice as far.
function controlShift(bow: number, direction: Direction) {
  return direction === "LR" ? { x: 0, y: bow * 2 } : { x: bow * 2, y: 0 };
}

function labelCentre(
  s: { x: number; y: number },
  e: { x: number; y: number },
  spot: { bow: number; t: number },
  direction: Direction,
) {
  const shift = controlShift(spot.bow, direction);
  const control = { x: (s.x + e.x) / 2 + shift.x, y: (s.y + e.y) / 2 + shift.y };
  return curvePoint(s, control, e, spot.t);
}

export type Size = { width: number; height: number };

function fitZoom({ width, height }: Bounds, size: Size): number {
  return Math.min(size.width / width, size.height / height);
}

/**
 * Which way to lay the twin out in a canvas of `size`: whichever direction
 * shows the whole map larger. Left to right wins unless top to bottom is
 * clearly better, so the layout does not flip on small resizes.
 */
export function chooseDirection(twin: CausalTwin, size: Size): Direction {
  if (!twin.edges.some(isPlaced)) return "LR";
  const lr = buildTwinGraph(twin, "LR").bounds;
  const tb = buildTwinGraph(twin, "TB").bounds;
  return fitZoom(tb, size) > fitZoom(lr, size) * 1.1 ? "TB" : "LR";
}
