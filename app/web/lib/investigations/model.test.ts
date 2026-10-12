import { describe, expect, it } from "vitest";
import recorded from "@/fixtures/synthetic-investigation.json";
import { InvestigationValidationError, current, parseInvestigations } from "./model";

const row = recorded.snapshot.find((r) => r.projection === "investigations")!;
const id = Object.keys(row.state)[0];

function variant(edit: (v: any) => void): unknown {
  const copy = structuredClone(row.state) as any;
  edit(copy[id]);
  return copy;
}

describe("parseInvestigations", () => {
  it("accepts the kernel's own projection", () => {
    const [inv] = parseInvestigations(row.state);
    expect(inv.phase).toBe("ASKING_HUMAN");
    expect(inv.next_action.kind).toBe("WAIT_FOR_PARENT_ANSWER");
    expect(inv.hypotheses).toHaveLength(2);
    expect(inv.uncertainty).toContain("COMPETING_EXPLANATIONS");
  });

  it("accepts every later state the kernel recorded", () => {
    for (const change of recorded.changes.filter((c) => c.projection === "investigations")) {
      expect(() => parseInvestigations(change.state)).not.toThrow();
    }
  });

  it("accepts older projections without inventing a history", () => {
    const [inv] = parseInvestigations(variant((v) => delete v.phase_history));
    expect(inv.phase_history).toBeUndefined();
  });

  it.each([
    ["a missing next action", (v: any) => delete v.next_action],
    ["an unknown next action", (v: any) => (v.next_action.kind = "DO_WHATEVER")],
    ["a next action for another phase", (v: any) => (v.next_action.phase = "EVALUATING")],
    ["masked competing explanations", (v: any) => (v.uncertainty = v.uncertainty.filter((u: string) => u !== "COMPETING_EXPLANATIONS"))],
    ["a scored uncertainty", (v: any) => v.uncertainty.push(0.7)],
    ["an invented uncertainty", (v: any) => v.uncertainty.push("FAIRLY_SURE")],
    ["repeated uncertainty", (v: any) => v.uncertainty.push(v.uncertainty[0])],
    ["an unknown phase", (v: any) => (v.phase = "DONE")],
    ["a malformed source domain", (v: any) => (v.evidence_requests[0].allowed_domains = ["not a host"])],
    ["a history ending in a different phase", (v: any) => (v.phase_history.at(-1).phase = "COMPLETE")],
    ["a history starting after opening", (v: any) => v.phase_history.shift()],
    ["a history in reverse order", (v: any) => v.phase_history.reverse()],
    ["duplicate history sequences", (v: any) => (v.phase_history[1].sequence = v.phase_history[0].sequence)],
    ["an invalid history timestamp", (v: any) => (v.phase_history[0].recorded_at = "yesterday")],
  ])("fails closed on %s", (_name, edit) => {
    expect(() => parseInvestigations(variant(edit))).toThrow(InvestigationValidationError);
  });

  it("picks the newest investigation still under way as current", () => {
    const [inv] = parseInvestigations(row.state);
    const finished = { ...inv, investigation_id: `inv_${"1".repeat(32)}`, phase: "COMPLETE" as const, opened_at: "2099-01-01T00:00:00Z" };
    expect(current([finished, inv])?.investigation_id).toBe(inv.investigation_id);
    expect(current([finished])?.investigation_id).toBe(finished.investigation_id);
    expect(current([])).toBeNull();
  });
});
