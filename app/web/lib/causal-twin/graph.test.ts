import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-causal-twin.json";
import { categorize } from "./categories";
import { buildTwinGraph, chooseDirection } from "./graph";
import { parseCausalTwin, type CausalTwin } from "./model";

const fixture = () => parseCausalTwin(payload);
const HYP = (n: number) => `hyp_${n.toString(16).padStart(32, "0")}`;

function withEdges(twin: CausalTwin, edges: CausalTwin["edges"]): CausalTwin {
  return { ...twin, edges };
}

describe("categorize", () => {
  it("reads the category off the kernel's verdict", () => {
    const byId = Object.fromEntries(fixture().edges.map((e) => [e.edge_id, categorize(e)]));
    expect(byId).toEqual({
      [HYP(1)]: "tested",
      [HYP(2)]: "observed",
      [HYP(3)]: "hypothesis",
      [HYP(4)]: "refuted",
      [HYP(5)]: "superseded",
      [HYP(6)]: "observed",
      [HYP(7)]: "hypothesis",
    });
  });

  it("does not promote an untested candidate that has experimental support", () => {
    const edge = { ...fixture().edges[1] };
    edge.support = [...edge.support, { entity_id: `out_${"0".repeat(31)}9`, kind: "EXPERIMENTAL" }];
    expect(categorize(edge)).toBe("observed");
  });
});

describe("buildTwinGraph", () => {
  it("draws one node per named variable and one edge per placed hypothesis", () => {
    const twin = fixture();
    const graph = buildTwinGraph(twin);
    expect(graph.nodes.map((n) => n.id).sort()).toEqual([
      "after_school_snack",
      "bedtime_resistance",
      "drop_off_distress",
      "late_bedtime",
      "morning_irritability",
      "screens_after_dinner",
    ]);
    expect(graph.edges.map((e) => e.id)).toEqual(
      twin.edges.filter((e) => e.cause && e.effect).map((e) => e.edge_id),
    );
    for (const edge of graph.edges) {
      const source = twin.edges.find((e) => e.edge_id === edge.id)!;
      expect([edge.source, edge.target]).toEqual([source.cause, source.effect]);
      expect(edge.data!.edge).toBe(source);
    }
  });

  it("keeps refuted and replaced links in the graph", () => {
    const graph = buildTwinGraph(fixture());
    expect(graph.edges.find((e) => e.id === HYP(4))?.data?.category).toBe("refuted");
    expect(graph.edges.find((e) => e.id === HYP(5))?.data?.category).toBe("superseded");
    expect(graph.counts).toEqual({ tested: 1, observed: 2, hypothesis: 2, refuted: 1, superseded: 1 });
  });

  it("lists a link with unnamed variables instead of guessing its endpoints", () => {
    const graph = buildTwinGraph(fixture());
    expect(graph.unplaced.map((e) => e.edge_id)).toEqual([HYP(7)]);
    expect(graph.edges.some((e) => e.id === HYP(7))).toBe(false);
  });

  it("follows the model: a new edge in the twin is a new edge on the map", () => {
    const twin = fixture();
    const extra = { ...twin.edges[2], edge_id: HYP(42), cause: "drop_off_distress", effect: "nap_length" };
    const graph = buildTwinGraph(withEdges(twin, [...twin.edges, extra]));
    expect(graph.edges).toHaveLength(7);
    expect(graph.edges.at(-1)).toMatchObject({ id: HYP(42), source: "drop_off_distress", target: "nap_length" });
    expect(graph.nodes.some((n) => n.id === "nap_length" && n.data.label === "Nap length")).toBe(true);

    const empty = buildTwinGraph(withEdges(twin, []));
    expect(empty.nodes).toEqual([]);
    expect(empty.edges).toEqual([]);
  });

  it("never draws two links between the same variables on one curve", () => {
    for (const direction of ["LR", "TB"] as const) {
      const graph = buildTwinGraph(fixture(), direction);
      const parallel = graph.edges.filter(
        (e) => e.source === "screens_after_dinner" && e.target === "bedtime_resistance",
      );
      expect(parallel).toHaveLength(2);
      const [a, b] = parallel.map((e) => JSON.stringify(e.data!.bow));
      expect(a).not.toBe(b);
    }
  });

  it("lays out causes before effects, deterministically, in either direction", () => {
    const twin = fixture();
    const lr = buildTwinGraph(twin, "LR");
    const x = Object.fromEntries(lr.nodes.map((n) => [n.id, n.position.x]));
    expect(x.screens_after_dinner).toBeLessThan(x.bedtime_resistance);
    expect(x.bedtime_resistance).toBeLessThan(x.late_bedtime);
    expect(x.late_bedtime).toBeLessThan(x.morning_irritability);
    expect(buildTwinGraph(twin, "LR")).toEqual(lr);

    const tb = buildTwinGraph(twin, "TB");
    const y = Object.fromEntries(tb.nodes.map((n) => [n.id, n.position.y]));
    expect(y.screens_after_dinner).toBeLessThan(y.bedtime_resistance);
  });

  it("still draws every edge when rival links form a cycle", () => {
    const twin = fixture();
    const back = { ...twin.edges[2], edge_id: HYP(43), cause: "drop_off_distress", effect: "bedtime_resistance" };
    const graph = buildTwinGraph(withEdges(twin, [...twin.edges, back]));
    expect(graph.edges.map((e) => e.id)).toContain(HYP(43));
    expect(graph.nodes).toHaveLength(6);
  });

  it("marks only the selected edge", () => {
    const graph = buildTwinGraph(fixture(), "LR", HYP(4));
    expect(graph.edges.filter((e) => e.data!.selected).map((e) => e.id)).toEqual([HYP(4)]);
  });

  it("lays the map out in whichever direction suits the canvas", () => {
    const twin = fixture();
    // The fixture is a chain five links long: wide canvases read it across,
    // narrow ones down.
    expect(chooseDirection(twin, { width: 1100, height: 540 })).toBe("LR");
    expect(chooseDirection(twin, { width: 600, height: 540 })).toBe("TB");
    expect(chooseDirection(twin, { width: 320, height: 540 })).toBe("TB");
    expect(chooseDirection(withEdges(twin, []), { width: 320, height: 540 })).toBe("LR");
  });
});
