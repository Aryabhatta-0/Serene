import { describe, expect, it } from "vitest";
import example from "@/fixtures/approval-command.example.json";
import payload from "@/fixtures/synthetic-experiments.json";
import {
  NotDecidable,
  buildApprovalCommand,
  canApprove,
  canDecide,
  newRequestId,
  parseApprovalResult,
} from "./approval";
import { parseExperimentsView, type Experiment } from "./model";

const view = parseExperimentsView(payload);
const awaiting = view.experiments.filter((e) => e.phase === "AWAITING_APPROVAL");
const green = awaiting.find((e) => e.safety_class === "GREEN")!;
const red = view.experiments.find((e) => e.safety_class === "RED")!;

describe("buildApprovalCommand", () => {
  it("builds exactly the command the kernel's channel is tested to accept", () => {
    // tests/test_web_approvals.py applies this same JSON through WebApprovalChannel.
    expect(buildApprovalCommand(green, "APPROVE", example.request_id)).toEqual(example);
  });

  it("quotes back what the parent was shown", () => {
    const command = buildApprovalCommand(green, "DECLINE", newRequestId());
    expect(command.shown_intervention_digest).toBe(green.approval!.intervention_digest);
    expect(command.shown_safety_class).toBe(green.approval!.safety_class);
    expect(command.decision).toBe("DECLINE");
  });

  it("can never build an approval for RED", () => {
    expect(canApprove(red)).toBe(false);
    expect(() => buildApprovalCommand(red, "APPROVE", newRequestId())).toThrow(NotDecidable);
    // Even a payload that slipped past the parser with RED and an open request.
    const forged: Experiment = {
      ...green,
      safety_class: "RED",
      approval: { ...green.approval!, safety_class: "RED" },
    };
    expect(canDecide(forged)).toBe(true);
    expect(canApprove(forged)).toBe(false);
    expect(() => buildApprovalCommand(forged, "APPROVE", newRequestId())).toThrow("RED");
  });

  it("refuses every experiment that is not awaiting a decision", () => {
    const closed = view.experiments.filter((e) => e.phase !== "AWAITING_APPROVAL");
    expect(closed.length).toBe(view.experiments.length - awaiting.length);
    for (const e of closed) {
      expect(canDecide(e)).toBe(false);
      expect(() => buildApprovalCommand(e, "DECLINE", newRequestId())).toThrow(NotDecidable);
    }
  });

  it("makes request ids the kernel accepts", () => {
    expect(newRequestId()).toMatch(/^[A-Za-z0-9_-]{16,64}$/);
    expect(newRequestId()).not.toBe(newRequestId());
  });
});

describe("parseApprovalResult", () => {
  it("reads the kernel's answers", () => {
    expect(parseApprovalResult({ outcome: "APPROVAL_GRANTED", reason_codes: [] })?.outcome).toBe("APPROVAL_GRANTED");
    expect(parseApprovalResult({ outcome: "REFUSED", reason_codes: ["APPROVAL_EXPIRED"] })?.outcome).toBe("REFUSED");
  });

  it.each([
    [null],
    [{ outcome: "OK" }],
    [{ outcome: "APPROVAL_GRANTED" }],
    [{ outcome: "REFUSED", reason_codes: [] }],
    [{ outcome: "REFUSED", reason_codes: ["not a code"] }],
  ])("never reads %j as an answer", (value) => {
    expect(parseApprovalResult(value)).toBeNull();
  });
});
