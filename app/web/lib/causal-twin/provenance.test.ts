import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-causal-twin.json";
import { parseCausalTwin, type CausalEdge, type CausalTwin } from "./model";
import {
  againstFor,
  competingLinks,
  entityKind,
  formatDate,
  lineageOf,
  supersessionOf,
  supportFor,
  verdictReason,
} from "./provenance";

const id = (prefix: string, n: number) => `${prefix}_${n.toString(16).padStart(32, "0")}`;
const twin = (): CausalTwin => parseCausalTwin(structuredClone(payload));
const edgeOf = (t: CausalTwin, n: number): CausalEdge => t.edges.find((e) => e.edge_id === id("hyp", n))!;

describe("provenance read from the kernel's edge", () => {
  it("names what an id refers to from its typed prefix", () => {
    expect(entityKind(id("evd", 1))).toBe("evidence");
    expect(entityKind(id("obs", 1))).toBe("observation");
    expect(entityKind(id("out", 1))).toBe("outcome");
    expect(entityKind(id("hyp", 1))).toBe("hypothesis");
    expect(entityKind(id("trl", 1))).toBe("other");
  });

  it("keeps observational and experimental support apart", () => {
    expect(supportFor(edgeOf(twin(), 1))).toEqual([
      { id: id("obs", 1), role: "observation" },
      { id: id("obs", 2), role: "observation" },
      { id: id("out", 1), role: "outcome-supports" },
    ]);
  });

  it("names each kind of counterevidence, contradicting outcomes first", () => {
    const base = edgeOf(twin(), 6);
    const edge: CausalEdge = {
      ...base,
      counterevidence: [id("evd", 9), id("obs", 7), id("out", 3), id("out", 4)],
      contradicting_outcomes: [id("out", 4)],
    };
    expect(againstFor(edge)).toEqual([
      { id: id("out", 4), role: "outcome-contradicts" },
      { id: id("evd", 9), role: "evidence-against" },
      { id: id("obs", 7), role: "observation-against" },
      // An outcome against it that does not contradict it is inconclusive
      // (Counterevidence.all_ids holds only those two kinds of outcome).
      { id: id("out", 3), role: "outcome-inconclusive" },
    ]);
  });

  it("resolves supersession and rivals by id, not by statement", () => {
    const t = twin();
    // Two links that read the same: only the id decides which one is meant.
    const lookalike: CausalEdge = { ...edgeOf(t, 5), edge_id: id("hyp", 8) };
    const doubled: CausalTwin = { ...t, edges: [...t.edges, lookalike] };
    expect(lookalike.relationship).toBe(edgeOf(t, 5).relationship);

    const replaces = supersessionOf(edgeOf(doubled, 1), doubled).replaces!;
    expect(replaces.id).toBe(id("hyp", 5));
    expect(replaces.edge).toBe(edgeOf(doubled, 5));
    expect(supersessionOf(edgeOf(doubled, 5), doubled).replacedBy.map((e) => e.edge_id)).toEqual([id("hyp", 1)]);
    expect(supersessionOf(lookalike, doubled).replacedBy).toEqual([]);

    const rivals = competingLinks({ ...edgeOf(t, 4), competing_edges: [id("hyp", 1), id("hyp", 99)] }, t);
    expect(rivals.map((r) => [r.id, r.edge?.edge_id ?? null])).toEqual([
      [id("hyp", 1), id("hyp", 1)],
      [id("hyp", 99), null],
    ]);
  });

  it("follows the chain from the link's parents to its raw evidence", () => {
    const t = twin();
    const edge = edgeOf(t, 1);
    expect(lineageOf(edge, t)).toEqual({
      parents: [{ id: id("pat", 1), edge: null }],
      raw: [
        { id: id("evd", 1), declared: true },
        { id: id("evd", 2), declared: true },
      ],
      unreached: [],
    });
    const partial = { ...edge, provenance: { ...edge.provenance, source_ids: [id("evd", 2), id("evd", 7)] } };
    expect(lineageOf(partial, t).raw).toEqual([
      { id: id("evd", 1), declared: false },
      { id: id("evd", 2), declared: true },
    ]);
    expect(lineageOf(partial, t).unreached).toEqual([id("evd", 7)]);
  });

  it("explains the verdict the kernel gave, and nothing stronger", () => {
    const t = twin();
    expect(verdictReason(edgeOf(t, 1))).toMatch(/^An experiment you approved supported it/);
    expect(verdictReason(edgeOf(t, 4))).toMatch(/^An experiment outcome contradicted it/);
    expect(verdictReason(edgeOf(t, 5))).toMatch(/set aside for a better-formed version/);
    expect(verdictReason(edgeOf(t, 2))).toMatch(/has not been tested/);
    expect(verdictReason(edgeOf(t, 7))).toMatch(/Nothing recorded supports it yet/);
    const contradicted = { ...edgeOf(t, 6), counterevidence: [id("out", 3)], contradicting_outcomes: [id("out", 3)] };
    expect(verdictReason(contradicted)).toMatch(/contradicts it, so it is not treated as established/);
  });

  it("writes kernel timestamps as UTC calendar dates", () => {
    expect(formatDate("2026-02-01T00:00:00Z")).toBe("1 February 2026");
    expect(formatDate("2026-03-31T23:30:00-02:00")).toBe("1 April 2026");
  });
});
