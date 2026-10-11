import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-memory-dream.json";
import { MemoryValidationError, parseMemoryDreamView } from "./model";
import { memorySourceFrom } from "./source";

// A deep copy of the fixture to break in one place.
function variant(edit: (v: any) => void): unknown {
  const copy = structuredClone(payload) as any;
  edit(copy);
  return copy;
}

const rejectedIndex = payload.patches.findIndex((p) => p.status === "REJECTED");
const committedIndex = payload.patches.findIndex((p) => p.status === "COMMITTED");

describe("parseMemoryDreamView", () => {
  it("accepts the kernel's own output", () => {
    const view = parseMemoryDreamView(payload);
    expect(view.memories).toHaveLength(1);
    expect(view.dream_runs).toHaveLength(2);
    expect(new Set(view.patches.map((p) => p.status))).toEqual(new Set(["COMMITTED", "REJECTED", "PROPOSED"]));
  });

  it("carries no child or actor identifiers", () => {
    const text = JSON.stringify(parseMemoryDreamView(payload));
    expect(text).not.toMatch(/chd_|act_|child_id|actor_id/);
  });

  it.each([
    ["a rejected patch without reasons", (v: any) => (v.patches[rejectedIndex].rejection_reasons = [])],
    ["reasons on a kept patch", (v: any) => (v.patches[committedIndex].rejection_reasons = ["MALFORMED_DIFF"])],
    ["a kept patch without a commit", (v: any) => (v.patches[committedIndex].commit_sha = null)],
    ["a decided patch without a decision time", (v: any) => (v.patches[rejectedIndex].decided_at = null)],
    ["a memory written by an unknown patch", (v: any) => (v.memories[0].written_by = `mpt_${"0".repeat(32)}`)],
    ["a memory written by a refused patch", (v: any) => (v.memories[0].written_by = v.patches[rejectedIndex].patch_id)],
    ["a run proposing an unknown patch", (v: any) => v.dream_runs[0].proposed.push(`mpt_${"1".repeat(32)}`)],
    ["stages out of order", (v: any) => v.dream_runs[0].stages.reverse()],
    ["a complete run missing a stage", (v: any) => v.dream_runs[0].stages.pop()],
    ["a dangling lineage parent", (v: any) => v.memories[0].lineage.nodes[0].parents.push(`obs_${"2".repeat(32)}`)],
    ["a malformed reason code", (v: any) => (v.patches[rejectedIndex].rejection_reasons = ["not a code"])],
    ["an unknown version", (v: any) => (v.version = "memory-dream-view/2")],
    ["a target outside memory", (v: any) => (v.patches[0].target_path = "../etc/passwd")],
  ])("fails closed on %s", (_name, edit) => {
    expect(() => parseMemoryDreamView(variant(edit))).toThrow(MemoryValidationError);
    expect(memorySourceFrom(variant(edit)).status).toBe("error");
  });

  it("accepts a lineage gap the kernel reported as missing", () => {
    const gap = `obs_${"3".repeat(32)}`;
    const view = parseMemoryDreamView(
      variant((v) => {
        v.memories[0].lineage.nodes[0].parents.push(gap);
        v.memories[0].lineage.missing.push(gap);
      }),
    );
    expect(view.memories[0].lineage.missing).toEqual([gap]);
  });
});
