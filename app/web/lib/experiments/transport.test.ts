import { describe, expect, it, vi } from "vitest";
import type { ApprovalCommand } from "./approval";
import { APPROVALS_ROUTE, TransportError, webApprovalTransport } from "./transport";

const CHILD = `chd_${"a".repeat(32)}`;
const COMMAND: ApprovalCommand = {
  approval_request_id: `apr_${"1".repeat(32)}`,
  decision: "APPROVE",
  shown_intervention_digest: "0".repeat(64),
  shown_safety_class: "GREEN",
  request_id: "web-0000000000000001",
};
const ANSWER = { outcome: "APPROVAL_GRANTED", event_ids: [`evt_${"2".repeat(32)}`], reason_codes: [] };

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("webApprovalTransport", () => {
  it("posts the command for the chosen child with the session token, and names no actor", async () => {
    const send = vi.fn(async () => json(200, ANSWER));
    const answer = await webApprovalTransport(CHILD, async () => "fake-access.token.value", send)(COMMAND);
    expect(answer).toEqual(ANSWER);
    const [url, init] = send.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(APPROVALS_ROUTE);
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers).toEqual({ "Content-Type": "application/json", Authorization: "Bearer fake-access.token.value" });
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ child_id: CHILD, command: COMMAND });
    expect(JSON.stringify(body)).not.toMatch(/actor|user_id|act_/);
  });

  it("sends nothing without a session", async () => {
    const send = vi.fn();
    await expect(webApprovalTransport(CHILD, async () => null, send)(COMMAND)).rejects.toEqual(
      new TransportError("signed-out"),
    );
    expect(send).not.toHaveBeenCalled();
  });

  it("never turns a failure into an answer", async () => {
    const token = async () => "fake-access.token.value";
    for (const [status, reason] of [
      [401, "signed-out"],
      [403, "refused"],
      [429, "refused"],
      [502, "refused"],
    ] as const) {
      const send = vi.fn(async () => json(status, { error: "X" }));
      await expect(webApprovalTransport(CHILD, token, send)(COMMAND)).rejects.toEqual(new TransportError(reason));
    }
    const offline = vi.fn(async () => {
      throw new TypeError("fetch failed");
    });
    await expect(webApprovalTransport(CHILD, token, offline)(COMMAND)).rejects.toEqual(
      new TransportError("unreachable"),
    );
  });
});
