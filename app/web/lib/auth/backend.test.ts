import type { SupabaseClient } from "@supabase/supabase-js";
import { describe, expect, it, vi } from "vitest";
import { supabaseBackend } from "./backend";

const USER = "00000000-0000-0000-0000-000000000001";
const A = `chd_${"a".repeat(32)}`;
const B = `chd_${"b".repeat(32)}`;

// A stand-in with exactly the supabase-js calls the backend makes.
function fakeClient(rows: { data: unknown[] | null; error: { message: string } | null }) {
  const calls: unknown[][] = [];
  let authListener: ((event: string, session: unknown) => void) | null = null;
  const unsubscribe = vi.fn();
  const query = {
    select: vi.fn((cols: string) => (calls.push(["select", cols]), query)),
    eq: vi.fn((col: string, value: string) => {
      calls.push(["eq", col, value]);
      return calls.filter((c) => c[0] === "eq").length === 2 ? Promise.resolve(rows) : query;
    }),
  };
  const auth = {
    onAuthStateChange: vi.fn((cb: (event: string, session: unknown) => void) => {
      authListener = cb;
      return { data: { subscription: { unsubscribe } } };
    }),
    signInWithPassword: vi.fn(),
    signOut: vi.fn(async () => ({ error: null })),
  };
  const client = {
    auth,
    schema: vi.fn((s: string) => (calls.push(["schema", s]), { from: (t: string) => (calls.push(["from", t]), query) })),
    channel: vi.fn(),
    removeChannel: vi.fn(),
  };
  return { client: client as unknown as SupabaseClient, auth, calls, unsubscribe, emit: (e: string, s: unknown) => authListener?.(e, s) };
}

describe("supabaseBackend", () => {
  it("lists only the signed-in user's own children as a parent, from the guardian registry", async () => {
    const fake = fakeClient({ data: [{ child_id: B }, { child_id: A }, { child_id: B }], error: null });
    expect(await supabaseBackend(fake.client).listChildren(USER)).toEqual([A, B]);
    expect(fake.calls).toEqual([
      ["schema", "serene"],
      ["from", "child_guardians"],
      ["select", "child_id"],
      ["eq", "user_id", USER],
      ["eq", "role", "PARENT"],
    ]);
  });

  it("refuses a malformed child id and surfaces a read error", async () => {
    await expect(
      supabaseBackend(fakeClient({ data: [{ child_id: "chd_x" }], error: null }).client).listChildren(USER),
    ).rejects.toThrow();
    await expect(
      supabaseBackend(fakeClient({ data: null, error: { message: "permission denied" } }).client).listChildren(USER),
    ).rejects.toThrow("permission denied");
  });

  it("reports only the opaque user id from a session, and unsubscribes", () => {
    const fake = fakeClient({ data: [], error: null });
    const seen: unknown[] = [];
    const stop = supabaseBackend(fake.client).onAuthChange((s) => seen.push(s));
    fake.emit("INITIAL_SESSION", null);
    fake.emit("SIGNED_IN", { access_token: "secret", user: { id: USER, email: "parent@example.org" } });
    fake.emit("SIGNED_OUT", null);
    expect(seen).toEqual([null, { userId: USER }, null]);
    stop();
    expect(fake.unsubscribe).toHaveBeenCalledOnce();
  });

  it("tells a wrong password apart from Serene being unreachable", async () => {
    const fake = fakeClient({ data: [], error: null });
    const backend = supabaseBackend(fake.client);
    fake.auth.signInWithPassword.mockResolvedValueOnce({ error: null });
    expect(await backend.signIn("p@example.org", "pw")).toEqual({ ok: true });
    fake.auth.signInWithPassword.mockResolvedValueOnce({ error: { status: 400, message: "Invalid login credentials" } });
    expect(await backend.signIn("p@example.org", "pw")).toEqual({ ok: false, reason: "credentials" });
    fake.auth.signInWithPassword.mockResolvedValueOnce({ error: { status: 503, message: "down" } });
    expect(await backend.signIn("p@example.org", "pw")).toEqual({ ok: false, reason: "unavailable" });
    fake.auth.signInWithPassword.mockRejectedValueOnce(new TypeError("fetch failed"));
    expect(await backend.signIn("p@example.org", "pw")).toEqual({ ok: false, reason: "unavailable" });
  });

  it("signs out of this browser only", async () => {
    const fake = fakeClient({ data: [], error: null });
    await supabaseBackend(fake.client).signOut();
    expect(fake.auth.signOut).toHaveBeenCalledWith({ scope: "local" });
  });
});
