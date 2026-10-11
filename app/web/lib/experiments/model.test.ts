import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-experiments.json";
import { ExperimentsValidationError, PHASES, parseExperimentsView } from "./model";
import { experimentsSourceFrom } from "./source";

function variant(edit: (v: any) => void): unknown {
  const copy = structuredClone(payload) as any;
  edit(copy);
  return copy;
}

const at = (phase: string) => payload.experiments.findIndex((e) => e.phase === phase);

describe("parseExperimentsView", () => {
  it("accepts the kernel's own output, with every lifecycle phase", () => {
    const view = parseExperimentsView(payload);
    expect(new Set(view.experiments.map((e) => e.phase))).toEqual(new Set(PHASES));
  });

  it("carries no child or actor identifiers", () => {
    expect(JSON.stringify(parseExperimentsView(payload))).not.toMatch(/chd_|act_|child_id|requested_of/);
  });

  it.each([
    [
      "a RED request open for a decision",
      (v: any) => {
        const e = v.experiments[at("AWAITING_APPROVAL")];
        e.safety_class = "RED";
        e.approval.safety_class = "RED";
      },
    ],
    ["a RED experiment that is running", (v: any) => (v.experiments[at("WAITING_FOR_OUTCOME")].safety_class = "RED")],
    ["an open decision on a running experiment", (v: any) => (v.experiments[at("WAITING_FOR_OUTCOME")].approval.decision_open = true)],
    ["an open decision on a closed request", (v: any) => (v.experiments[at("PARKED_UNRESOLVED")].approval.decision_open = true)],
    ["a request rated differently from its experiment", (v: any) => (v.experiments[at("AWAITING_APPROVAL")].approval.safety_class = "AMBER")],
    ["a blocked experiment without reasons", (v: any) => (v.experiments[at("BLOCKED")].blocked_reasons = [])],
    ["a finished experiment without outcomes", (v: any) => (v.experiments[at("COMPLETED")].outcomes = [])],
    ["an unknown phase", (v: any) => (v.experiments[0].phase = "SUCCEEDED")],
    ["a non-boolean reversibility", (v: any) => (v.experiments[0].intervention.reversible = "yes")],
    ["an unknown version", (v: any) => (v.version = "experiments-view/2")],
  ])("fails closed on %s", (_name, edit) => {
    expect(() => parseExperimentsView(variant(edit))).toThrow(ExperimentsValidationError);
    expect(experimentsSourceFrom(variant(edit)).status).toBe("error");
  });
});
