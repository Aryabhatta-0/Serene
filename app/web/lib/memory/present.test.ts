import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-memory-dream.json";
import { parseMemoryDreamView } from "./model";
import { explainReason, proposedTitle, runPatches } from "./present";

const view = parseMemoryDreamView(payload);

describe("explainReason", () => {
  it("explains insufficient evidence with the rungs it names", () => {
    const reason = explainReason("INSUFFICIENT_EVIDENCE:OBSERVATION_BELOW_PATTERN");
    expect(reason.known).toBe(true);
    expect(reason.text).toBe(
      "Not enough evidence: it rests on an observation, and this kind of memory needs at least a pattern.",
    );
  });

  it("keeps an unknown code and says it has no plain description", () => {
    const reason = explainReason("SOMETHING_NEW:detail");
    expect(reason).toEqual({
      code: "SOMETHING_NEW:detail",
      text: "Recorded reason (Serene has no plain description for this code yet).",
      known: false,
    });
  });

  it("explains every reason recorded in the fixture", () => {
    const codes = [
      ...view.patches.flatMap((p) => [...p.rejection_reasons, ...(p.review?.reason_codes ?? [])]),
      ...view.dream_runs.flatMap((r) => r.stages.flatMap((s) => s.reason_codes)),
    ];
    expect(codes.length).toBeGreaterThan(0);
    for (const code of codes) expect(explainReason(code).known).toBe(true);
  });

  it("explains a refusal relayed from the record by its own code", () => {
    expect(explainReason("PROPOSAL_REFUSED:STALE_BASE_REVISION").text).toBe(
      "The record refused a proposal: The memory changed after this was proposed, so it was not applied.",
    );
  });
});

describe("proposedTitle", () => {
  it("reads the title line of the proposed text", () => {
    const rejected = view.patches.find((p) => p.status === "REJECTED")!;
    expect(proposedTitle(rejected)).toBe("Needs a warning before every transition");
  });
});

describe("runPatches", () => {
  it("groups a run's proposals by outcome, keeping the run's order", () => {
    const oldest = view.dream_runs[view.dream_runs.length - 1];
    const groups = runPatches(oldest, view);
    expect(groups.COMMITTED.map((p) => p.target_path)).toEqual(["learnings/pickup-heads-up.md"]);
    expect(groups.REJECTED.map((p) => p.target_path)).toEqual(["child/needs-warning-before-every-transition.md"]);
    expect(groups.PROPOSED).toEqual([]);
  });
});
