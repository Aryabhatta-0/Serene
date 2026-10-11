import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-causal-twin.json";
import { parseCausalTwin, twinVariables, TwinValidationError } from "./model";
import { twinSourceFrom } from "./source";

// The fixture is synthetic and was validated against the kernel's own
// `CausalTwin.model_validate_json` (it round-trips through model_dump_json).
function mutated(change: (twin: any) => void): unknown {
  const twin = structuredClone(payload);
  change(twin);
  return twin;
}

const HYP = (n: number) => `hyp_${n.toString(16).padStart(32, "0")}`;

describe("parseCausalTwin", () => {
  it("accepts a twin in the kernel's wire format", () => {
    const twin = parseCausalTwin(payload);
    expect(twin.edges).toHaveLength(7);
    expect(twin.edges.map((e) => e.status)).toEqual([
      "SUPPORTED",
      "CANDIDATE",
      "CANDIDATE",
      "REFUTED",
      "SUPERSEDED",
      "CANDIDATE",
      "CANDIDATE",
    ]);
  });

  it("derives the same variables as CausalTwin.variables", () => {
    // From the kernel: CausalTwin.model_validate_json(fixture).variables
    expect(twinVariables(parseCausalTwin(payload))).toEqual([
      "after_school_snack",
      "bedtime_resistance",
      "drop_off_distress",
      "late_bedtime",
      "morning_irritability",
      "screens_after_dinner",
    ]);
  });

  it("rejects an edge without lineage provenance", () => {
    const bad = mutated((t) => (t.edges[1].provenance.derived_from = []));
    expect(() => parseCausalTwin(bad)).toThrow(/requires lineage provenance/);
    const noSources = mutated((t) => (t.edges[1].provenance.source_ids = []));
    expect(() => parseCausalTwin(noSources)).toThrow(TwinValidationError);
  });

  it("rejects an edge without raw evidence", () => {
    expect(() => parseCausalTwin(mutated((t) => (t.edges[1].raw_evidence = [])))).toThrow(
      /raw_evidence/,
    );
  });

  it("never lets observational support alone draw a link as tested", () => {
    const bad = mutated((t) => {
      t.edges[0].support = t.edges[0].support.filter((s: any) => s.kind === "OBSERVATIONAL");
    });
    expect(() => parseCausalTwin(bad)).toThrow(/observational support alone/);
  });

  it("rejects SUPPORTED below the tested rung, or with a contradiction", () => {
    expect(() =>
      parseCausalTwin(mutated((t) => ((t.edges[0].epistemic_level = 3), (t.edges[0].validity = null)))),
    ).toThrow(/at least a tested hypothesis/);
    expect(() =>
      parseCausalTwin(
        mutated((t) => {
          t.edges[0].counterevidence = [t.edges[3].contradicting_outcomes[0]];
          t.edges[0].contradicting_outcomes = [t.edges[3].contradicting_outcomes[0]];
        }),
      ),
    ).toThrow(/contradicted edge cannot be SUPPORTED/);
    expect(() =>
      parseCausalTwin(mutated((t) => (t.edges[0].learning_status = "STALE"))),
    ).toThrow(/stale or retest-pending/);
  });

  it("rejects REFUTED without the contradicting outcome", () => {
    const bad = mutated((t) => (t.edges[3].contradicting_outcomes = []));
    expect(() => parseCausalTwin(bad)).toThrow(/must cite the contradicting outcome/);
  });

  it("rejects a level-5 edge without its validity window", () => {
    expect(() => parseCausalTwin(mutated((t) => (t.edges[0].validity = null)))).toThrow(
      /validity window/,
    );
  });

  it("rejects malformed identifiers, unknown states and foreign edges", () => {
    expect(() => parseCausalTwin(mutated((t) => (t.edges[0].edge_id = "edge-1")))).toThrow(
      /hyp_ id/,
    );
    expect(() => parseCausalTwin(mutated((t) => (t.edges[0].status = "PROBABLE")))).toThrow(
      /status/,
    );
    expect(() =>
      parseCausalTwin(mutated((t) => (t.edges[1].epistemic_level = 0.75))),
    ).toThrow(/epistemic_level/);
    expect(() =>
      parseCausalTwin(
        mutated((t) => {
          const other = `chd_${"9".repeat(32)}`;
          t.edges[1].child_id = other;
          t.edges[1].scope.child_id = other;
        }),
      ),
    ).toThrow(/another child/);
    expect(() => parseCausalTwin(mutated((t) => (t.edges[1].edge_id = HYP(1))))).toThrow(
      /duplicate edge id/,
    );
    expect(() => parseCausalTwin(mutated((t) => (t.twin_version = "causal-twin/2")))).toThrow(
      /twin_version/,
    );
  });

  it("does not carry fields the kernel does not define", () => {
    const twin = parseCausalTwin(mutated((t) => (t.edges[1].confidence = 0.92)));
    expect(twin.edges[1]).not.toHaveProperty("confidence");
  });
});

describe("twinSourceFrom", () => {
  it("turns an invalid payload into an error state, never a partial map", () => {
    const source = twinSourceFrom(mutated((t) => (t.edges[3].contradicting_outcomes = [])));
    expect(source.status).toBe("error");
    expect(twinSourceFrom(null).status).toBe("error");
    expect(twinSourceFrom(payload).status).toBe("ready");
  });
});
