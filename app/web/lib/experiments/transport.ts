import type { ApprovalTransport } from "./approval";

// The web app's real approval transport (Issue #84). It sends the command the
// parent confirmed, with the chosen child and the signed-in session's access
// token, to the app's own /api/approvals route, which relays it to the kernel.
// It never names who is deciding (the kernel takes that from the verified
// session) and never synthesizes an answer: anything but the kernel's 200
// reply is a failure, and the surface shows nothing as decided.

export class TransportError extends Error {
  constructor(readonly reason: "signed-out" | "refused" | "unreachable") {
    super(reason);
    this.name = "TransportError";
  }
}

export const APPROVALS_ROUTE = "/api/approvals";

export function webApprovalTransport(
  childId: string,
  accessToken: () => Promise<string | null>,
  send: typeof fetch = (...args) => fetch(...args),
): ApprovalTransport {
  return async (command) => {
    const token = await accessToken();
    if (!token) throw new TransportError("signed-out");
    let response: Response;
    try {
      response = await send(APPROVALS_ROUTE, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ child_id: childId, command }),
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch {
      throw new TransportError("unreachable");
    }
    if (response.status === 401) throw new TransportError("signed-out");
    if (response.status !== 200) throw new TransportError("refused");
    return response.json();
  };
}
