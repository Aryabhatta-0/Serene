import { describe, expect, it } from "vitest";
import { nextSession, type SessionState } from "./session";

const A = { userId: "00000000-0000-0000-0000-000000000001" };
const B = { userId: "00000000-0000-0000-0000-000000000002" };
const signedIn = (s: typeof A): SessionState => ({ status: "signed-in", userId: s.userId });

describe("nextSession", () => {
  it("no stored session on load is signed out, not expired", () => {
    expect(nextSession({ status: "loading" }, null, false)).toEqual({ status: "signed-out" });
  });

  it("a session signs in, and the same user stays the same state", () => {
    const first = nextSession({ status: "loading" }, A, false);
    expect(first).toEqual(signedIn(A));
    expect(nextSession(first, A, false)).toBe(first); // a token refresh changes nothing shown
  });

  it("a different user is a new state", () => {
    expect(nextSession(signedIn(A), B, false)).toEqual(signedIn(B));
  });

  it("losing the session without signing out is an expiry, and stays one until sign-in", () => {
    const expired = nextSession(signedIn(A), null, false);
    expect(expired).toEqual({ status: "expired" });
    expect(nextSession(expired, null, false)).toEqual({ status: "expired" });
    expect(nextSession(expired, A, false)).toEqual(signedIn(A));
  });

  it("signing out is a sign-out, not an expiry", () => {
    expect(nextSession(signedIn(A), null, true)).toEqual({ status: "signed-out" });
  });
});
