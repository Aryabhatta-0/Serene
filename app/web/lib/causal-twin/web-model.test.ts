import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-causal-twin-web.json";
import kernel from "@/fixtures/synthetic-twin-provenance.json";
import { citedIds } from "./provenance-model";
import { twinSourceFromProjection } from "./source";
import { parseWebTwin, WEB_TWIN_VERSION } from "./web-model";

// The live `causal_twin` projection (serene/causal/web.py). The fixture is
// kernel output: the #75 fixture family, as the row the publisher writes.
const HEAD = payload.ledger_head;
function mutated(change: (twin: any) => void): unknown {
  const twin = structuredClone(payload) as any;
  change(twin);
  return twin;
}
const PRIVATE = /\b(chd|act|src)_[0-9a-f]{32}\b/;

describe("parseWebTwin", () => {
  it("reads the projection into the same twin and provenance as the kernel format", () => {
    const { twin, provenance, asOf } = parseWebTwin(structuredClone(payload));
    expect(payload.version).toBe(WEB_TWIN_VERSION);
    expect(asOf).toBe(payload.as_of);
    expect(twin.edges.map((e) => [e.edge_id, e.status, e.cause, e.effect])).toEqual(
      kernel.twin.edges.map((e) => [e.edge_id, e.status, e.cause, e.effect]),
    );
    for (const edge of twin.edges) {
      const raw = kernel.twin.edges.find((e) => e.edge_id === edge.edge_id)!;
      expect(edge.support).toEqual(raw.support);
      expect(edge.counterevidence).toEqual(raw.counterevidence);
      expect(edge.contradicting_outcomes).toEqual(raw.contradicting_outcomes);
      expect(edge.experiments).toEqual(raw.experiments);
      expect(edge.raw_evidence).toEqual(raw.raw_evidence);
      expect(edge.scope.contexts).toEqual(raw.scope.contexts);
      expect(edge.provenance.created_by.kind).toBe(raw.provenance.created_by.kind);
      // Every edge has its complete provenance, and every link it cites lands.
      const detail = provenance.edges.get(edge.edge_id)!;
      for (const id of citedIds(detail)) expect(provenance.nodes.has(id) || provenance.missing.has(id)).toBe(true);
    }
    expect(provenance.edges.size).toBe(kernel.provenance.edges.length);
  });

  it("holds no child, actor or source id, in the payload or the view model", () => {
    expect(JSON.stringify(payload)).not.toMatch(PRIVATE);
    const { twin, provenance } = parseWebTwin(structuredClone(payload));
    const kept = JSON.stringify({ twin, nodes: [...provenance.nodes.values()], edges: [...provenance.edges.values()] });
    expect(kept).not.toMatch(PRIVATE);
    expect(kept).not.toMatch(/"(child_id|actor_id|source_id|user_id)"/);
    expect(kept).not.toContain(kernel.twin.child_id);
  });

  it("refuses a payload that carries a private identifier", () => {
    const child = kernel.twin.child_id;
    expect(() => parseWebTwin(mutated((t) => (t.child_id = child)))).toThrow(/private identifier/);
    expect(() => parseWebTwin(mutated((t) => (t.edges[0].origin.actor_id = `act_${"1".repeat(32)}`)))).toThrow(
      /private identifier/,
    );
    expect(() => parseWebTwin(mutated((t) => (t.edges[0].confounders = [`src_${"2".repeat(32)}`])))).toThrow(
      /private identifier/,
    );
  });

  it("fails closed when the twin and its provenance disagree", () => {
    expect(() => parseWebTwin(mutated((t) => (t.version = "causal-twin/1")))).toThrow(/version/);
    expect(() => parseWebTwin(mutated((t) => (t.edges[0].status = "CANDIDATE")))).toThrow(/verdict differs/);
    expect(() => parseWebTwin(mutated((t) => (t.provenance.ledger_head = "0".repeat(64))))).toThrow(/another ledger position/);
    expect(() => parseWebTwin(mutated((t) => t.provenance.edges.pop()))).toThrow(/does not match|no provenance/);
    expect(() => parseWebTwin(mutated((t) => (t.edges[1].experiments = [])))).toThrow(/differs from the edge/);
    expect(() => parseWebTwin(mutated((t) => (t.edges[1].counterevidence = [t.edges[1].raw_evidence[0]])))).toThrow(/differs from the edge/);
    expect(() => parseWebTwin(mutated((t) => (t.provenance.as_of = "2030-01-01T00:00:00Z")))).toThrow(/another time/);
  });

  it("fails closed on nodes the edges do not name, or names that are not nodes", () => {
    expect(() => parseWebTwin(mutated((t) => (t.edges[0].from_node = `var_${"f".repeat(32)}`)))).toThrow(/names no node/);
    expect(() => parseWebTwin(mutated((t) => (t.edges[0].to_node = null)))).toThrow(/both of its variables or neither/);
    expect(() =>
      parseWebTwin(mutated((t) => t.nodes.push({ node_id: `var_${"e".repeat(32)}`, type: "VARIABLE", label: "unused" }))),
    ).toThrow(/exactly the variables/);
    expect(() => parseWebTwin(mutated((t) => (t.nodes[0].type = "PERSON")))).toThrow(/VARIABLE/);
  });

  it("draws a link with no named variables in the list, not between guessed endpoints", () => {
    const unplaced = mutated((t) => {
      for (const e of t.edges) e.from_node = e.to_node = null;
      t.nodes = [];
    });
    const { twin } = parseWebTwin(unplaced);
    expect(twin.edges.every((e) => e.cause === null && e.effect === null)).toBe(true);
  });
});

describe("twinSourceFromProjection", () => {
  it("is an empty map before any hypothesis, and an error on a bad row", () => {
    expect(twinSourceFromProjection({}, HEAD)).toEqual({ status: "ready", twin: { ledger_head: HEAD, edges: [] } });
    expect(twinSourceFromProjection({ version: "causal-twin-web/1" }, HEAD).status).toBe("error");
    expect(twinSourceFromProjection(structuredClone(payload) as Record<string, unknown>, HEAD).status).toBe("ready");
  });
});
