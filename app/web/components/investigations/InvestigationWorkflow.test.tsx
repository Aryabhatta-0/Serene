import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import recorded from "@/fixtures/synthetic-investigation.json";
import { parseInvestigations, type Investigation } from "@/lib/investigations/model";
import { investigationStages } from "@/lib/investigations/present";
import { InvestigationWorkflow } from "./InvestigationWorkflow";

const [inv] = parseInvestigations(recorded.snapshot.find((r) => r.projection === "investigations")!.state);

describe("recorded workflow", () => {
  it("shows the backend history by default, including times, reasons and waiting for the parent", () => {
    render(<InvestigationWorkflow investigation={inv} />);
    expect(screen.getByRole("status")).toHaveTextContent("Waiting for you");
    const list = screen.getByRole("list", { name: "Recorded investigation steps" });
    const steps = within(list).getAllByRole("listitem").filter((s) => s.hasAttribute("data-workflow-sequence"));
    expect(steps.map((s) => Number(s.dataset.workflowSequence))).toEqual(inv.phase_history!.map((s) => s.sequence));
    expect(steps[0]).toBeVisible();
    expect(steps.at(-1)).toHaveAttribute("aria-current", "step");
    expect(steps.at(-1)).toHaveTextContent("Waiting for you");
    for (const [i, step] of inv.phase_history!.entries()) {
      expect(steps[i].querySelector("time")).toHaveAttribute("datetime", step.recorded_at);
      for (const reason of step.reason_codes) expect(steps[i]).toHaveTextContent(reason);
    }
  });

  it("updates from new projection state without retaining another investigation's steps", () => {
    const { rerender } = render(<InvestigationWorkflow investigation={inv} />);
    const row = recorded.changes.filter((r) => r.projection === "investigations").at(-1)!;
    const [finished] = parseInvestigations(row.state);
    rerender(<InvestigationWorkflow investigation={finished} />);
    expect(screen.getByRole("status")).toHaveTextContent("Finished");
    expect(document.querySelectorAll("[data-workflow-sequence]")).toHaveLength(finished.phase_history!.length);
    rerender(<InvestigationWorkflow investigation={{ ...inv, phase_history: undefined }} />);
    expect(screen.getByText(/Earlier steps were not included/)).toBeVisible();
    expect(document.querySelectorAll("[data-workflow-sequence]")).toHaveLength(0);
  });

  it("keeps repeat visits in recorded order and calls a paused investigation paused", () => {
    const history = [
      ...inv.phase_history!,
      { sequence: 100, phase: "NEEDS_EVIDENCE" as const, recorded_at: inv.opened_at, reason_codes: [] },
      { sequence: 101, phase: "PARKED_UNRESOLVED" as const, recorded_at: inv.opened_at, reason_codes: ["PARENT_NO_RESPONSE"] },
    ];
    const paused: Investigation = { ...inv, phase: "PARKED_UNRESOLVED", phase_history: history,
      next_action: { ...inv.next_action, kind: "NONE_PARKED", phase: "PARKED_UNRESOLVED" } };
    render(<InvestigationWorkflow investigation={paused} />);
    expect(document.querySelectorAll('[data-workflow-phase="NEEDS_EVIDENCE"]')).toHaveLength(2);
    expect(screen.getByRole("status")).toHaveTextContent("Paused without an answer");
    expect(document.querySelector("[data-latest]")).toHaveTextContent("PARENT_NO_RESPONSE");
  });

  it("does not mark skipped stages as passed just because an investigation finished", () => {
    const stages = investigationStages({ phase: "COMPLETE", phase_history: [
      { sequence: 1, phase: "UNDERSTANDING", recorded_at: inv.opened_at, reason_codes: [] },
      { sequence: 2, phase: "COMPLETE", recorded_at: inv.opened_at, reason_codes: [] },
    ] });
    expect(stages.find((s) => s.key === "understand")?.state).toBe("done");
    expect(stages.find((s) => s.key === "verify")?.state).toBe("unrecorded");
    expect(stages.find((s) => s.key === "end")?.state).toBe("current");
  });
});
