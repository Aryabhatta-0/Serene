import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-twin-provenance.json";
import { chainOf } from "./chain";
import { parseCausalTwin, TwinValidationError } from "./model";
import { citedIds, pairWithTwin, parseTwinProvenance } from "./provenance-model";
import { twinSourceFrom } from "./source";

// The fixture is kernel output (tests/twin_provenance_fixture.py), pinned
// byte for byte by tests/test_twin_provenance.py.
const raw = () => structuredClone(payload.provenance) as unknown as Record<string, any>;
const twin = () => parseCausalTwin(structuredClone(payload.twin));
const parse = () => parseTwinProvenance(raw());

function rejects(mutate: (p: Record<string, any>) => void, message: RegExp) {
  const p = raw();
  mutate(p);
  expect(() => parseTwinProvenance(p)).toThrow(TwinValidationError);
  expect(() => parseTwinProvenance(p)).toThrow(message);
}
const edgeWith = (p: Record<string, any>, status: string) => p.edges.find((e: any) => e.status === status);

describe("parseTwinProvenance", () => {
  it("accepts the kernel's projection and pairs it with its twin", () => {
    const provenance = parse();
    expect(pairWithTwin(twin(), provenance)).toBe(provenance);
    expect([...provenance.edges.values()].map((e) => e.status).sort()).toEqual(["REFUTED", "SUPERSEDED", "SUPPORTED"]);
  });

  it("survives a JSON round trip unchanged", () => {
    const again = parseTwinProvenance(JSON.parse(JSON.stringify(raw())));
    expect(again).toEqual(parse());
  });

  it("resolves every edge to raw evidence, through every intermediate node", () => {
    const provenance = parse();
    for (const edge of provenance.edges.values()) {
      expect(edge.lineage.complete).toBe(true);
      const chain = chainOf(edge, provenance);
      expect(chain.missing).toEqual([]);
      const kinds = chain.lineage.map((e) => e.node?.kind);
      expect(kinds[0]).toBe("HYPOTHESIS");
      expect(kinds).toEqual(expect.arrayContaining(["PATTERN", "OBSERVATION", "EVIDENCE"]));
      expect(chain.lineage.filter((e) => e.node?.kind === "EVIDENCE").map((e) => e.id).sort()).toEqual(
        [...edge.lineage.raw_evidence].sort(),
      );
      for (const id of citedIds(edge)) {
        const node = provenance.nodes.get(id)!;
        expect(node.raw_evidence.length).toBeGreaterThan(0);
      }
    }
  });

  it("tells external evidence from family evidence", () => {
    const provenance = parse();
    const external = [...provenance.nodes.values()].filter((n) => n.evidence?.external);
    expect(external).toHaveLength(1);
    expect(external[0].evidence).toMatchObject({ source_kind: "BROWSER", evidence_kind: "BROWSER_CAPTURE", source_host: "example.org" });
    const learned = [...provenance.edges.values()].find((e) => e.epistemic_level === 5)!;
    const origins = new Set(learned.support.map((s) => provenance.nodes.get(s.entity_id)!.evidence_origin));
    expect(origins.has("EXTERNAL")).toBe(true);
    expect(origins.has("FAMILY")).toBe(true);
  });

  it("keeps outcome → experiment links, supersession and refutation reasons", () => {
    const provenance = parse();
    for (const edge of provenance.edges.values()) {
      for (const x of edge.experiments) for (const o of x.outcomes) expect(o.experiment_id).toBe(x.experiment_id);
    }
    const edges = [...provenance.edges.values()];
    const superseded = edges.find((e) => e.status === "SUPERSEDED")!;
    expect(superseded.supersession.reason).toBe("Narrowed to pickups after the posted pickup window");
    expect(superseded.supersession.superseded_by).toBe(edges.find((e) => e.status === "SUPPORTED")!.edge_id);
    const refuted = edges.find((e) => e.status === "REFUTED")!;
    expect(refuted.refutation).toEqual({
      reason_codes: ["CONTRADICTING_OUTCOME"],
      outcome_ids: [refuted.experiments[0].outcomes[0].outcome_id],
    });
  });

  it("carries the level-5 learning's scope, validity and review", () => {
    const learned = [...parse().edges.values()].find((e) => e.epistemic_level === 5)!;
    expect(learned.learning).not.toBeNull();
    expect(learned.validity).not.toBeNull();
    expect(learned.learning!.scope_contexts.length).toBeGreaterThan(0);
    expect(learned.learning!.review_after).toBe(learned.validity!.review_after);
  });

  it("refuses family identifiers", () => {
    rejects((p) => {
      p.nodes[0].origin.derived_from = ["act_" + "0".repeat(32)];
    }, /family identifier/);
    rejects((p) => {
      p.edges[0].edge_id = "chd_" + "0".repeat(32);
    }, /hyp_ id/);
  });

  it("refuses a link that does not resolve", () => {
    rejects((p) => {
      const dropped = p.edges[0].lineage.steps[1].entity_id;
      p.nodes = p.nodes.filter((n: any) => n.entity_id !== dropped);
    }, /unresolved provenance ids/);
  });

  it("refuses illegal edge states", () => {
    rejects((p) => {
      edgeWith(p, "REFUTED").refutation = null;
    }, /refutation detail/);
    rejects((p) => {
      edgeWith(p, "SUPPORTED").learning = null;
    }, /level-5/);
    rejects((p) => {
      edgeWith(p, "SUPERSEDED").supersession.reason = null;
    }, /supersession reason/);
    rejects((p) => {
      const exps = p.edges.flatMap((e: any) => e.experiments);
      exps[0].outcomes.push({ ...exps[1].outcomes[0] });
    }, /its own outcomes/);
    rejects((p) => {
      p.edges[0].lineage.complete = false;
    }, /complete/);
  });

  it("refuses a projection that explains a different twin", () => {
    const other = { ...raw(), ledger_head: "0".repeat(64) };
    expect(twinSourceFrom(structuredClone(payload.twin), other)).toMatchObject({ status: "error" });
    const ready = twinSourceFrom(structuredClone(payload.twin), raw());
    expect(ready.status).toBe("ready");
  });
});

describe("chainOf", () => {
  it("keeps a missing node in the chain instead of dropping it", () => {
    const p = raw();
    const edge = edgeWith(p, "REFUTED");
    const pattern = edge.lineage.steps.find((s: any) => s.entity_id.startsWith("pat_")).entity_id;
    p.nodes = p.nodes.filter((n: any) => n.entity_id !== pattern);
    p.missing = [{ entity_id: pattern, referenced_by: [edge.edge_id] }];
    edge.lineage.steps = edge.lineage.steps.filter((s: any) => s.entity_id !== pattern);
    edge.lineage.missing = [{ entity_id: pattern, referenced_by: [edge.edge_id] }];
    edge.lineage.complete = false;
    // Other edges that reached the pattern now reach a gap too.
    for (const other of p.edges) {
      if (other !== edge && other.lineage.steps.some((s: any) => s.entity_id === pattern)) {
        other.lineage.steps = other.lineage.steps.filter((s: any) => s.entity_id !== pattern);
        other.lineage.missing = [{ entity_id: pattern, referenced_by: [other.edge_id] }];
        other.lineage.complete = false;
      }
    }
    const provenance = parseTwinProvenance(p);
    const chain = chainOf(provenance.edges.get(edge.edge_id)!, provenance);
    expect(chain.complete).toBe(false);
    expect(chain.missing.map((m) => m.entity_id)).toEqual([pattern]);
    expect(chain.lineage.some((e) => e.id === pattern && e.node === null)).toBe(true);
  });
});
