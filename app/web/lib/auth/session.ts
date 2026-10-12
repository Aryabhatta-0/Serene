import type { AuthSnapshot } from "./backend";

// The web app's sign-in state (Issue #87). "expired" is a session that ended
// without the parent signing out (its refresh was refused, or it was revoked):
// it is said plainly, and nothing from the record stays on screen.
export type SessionState =
  | { status: "unconfigured" }
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "expired" }
  | { status: "signed-in"; userId: string };

export function nextSession(prev: SessionState, session: AuthSnapshot, signingOut: boolean): SessionState {
  if (session) {
    return prev.status === "signed-in" && prev.userId === session.userId
      ? prev
      : { status: "signed-in", userId: session.userId };
  }
  if (signingOut) return { status: "signed-out" };
  if (prev.status === "signed-in" || prev.status === "expired") return { status: "expired" };
  return { status: "signed-out" };
}
