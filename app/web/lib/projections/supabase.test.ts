import type { SupabaseClient } from "@supabase/supabase-js";
import { describe, expect, it, vi } from "vitest";
import { supabaseProjectionFeed } from "./supabase";
import { CHILD, row } from "./testing";

// A stand-in with the exact supabase-js calls the feed makes, recording them.
function fakeClient(result: { data: unknown[] | null; error: { message: string } | null }) {
  const calls: Record<string, unknown[]> = {};
  let listener: ((payload: unknown) => void) | null = null;
  let onStatus: ((status: string) => void) | null = null;
  const channel = {
    on: vi.fn((type: string, filter: unknown, cb: (payload: unknown) => void) => {
      calls.on = [type, filter];
      listener = cb;
      return channel;
    }),
    subscribe: vi.fn((cb: (status: string) => void) => {
      onStatus = cb;
      return channel;
    }),
  };
  const query = {
    select: vi.fn((cols: string) => ((calls.select = [cols]), query)),
    eq: vi.fn(async (col: string, value: string) => ((calls.eq = [col, value]), result)),
  };
  const client = {
    schema: vi.fn((s: string) => ((calls.schema = [s]), { from: (t: string) => ((calls.from = [t]), query) })),
    channel: vi.fn((name: string) => ((calls.channel = [name]), channel)),
    removeChannel: vi.fn(async () => "ok"),
  };
  return {
    client: client as unknown as SupabaseClient,
    raw: client,
    calls,
    deliver: (payload: unknown) => listener?.(payload),
    status: (s: string) => onStatus?.(s),
  };
}

describe("supabaseProjectionFeed", () => {
  it("reads the snapshot from serene.projection_state for one child only", async () => {
    const fake = fakeClient({ data: [row("active_investigations", 3)], error: null });
    const rows = await supabaseProjectionFeed(fake.client).fetchSnapshot(CHILD);
    expect(rows).toHaveLength(1);
    expect(fake.calls.schema).toEqual(["serene"]);
    expect(fake.calls.from).toEqual(["projection_state"]);
    expect(fake.calls.eq).toEqual(["child_id", CHILD]);
  });

  it("surfaces a read error instead of an empty state", async () => {
    const fake = fakeClient({ data: null, error: { message: "permission denied" } });
    await expect(supabaseProjectionFeed(fake.client).fetchSnapshot(CHILD)).rejects.toThrow("permission denied");
  });

  it("subscribes to this child's projection_state changes and maps every channel status", () => {
    const fake = fakeClient({ data: [], error: null });
    const rows: unknown[] = [];
    const statuses: string[] = [];
    const stop = supabaseProjectionFeed(fake.client).subscribe(CHILD, {
      onRow: (r) => rows.push(r),
      onStatus: (s) => statuses.push(s),
    });
    expect(fake.calls.on).toEqual([
      "postgres_changes",
      { event: "*", schema: "serene", table: "projection_state", filter: `child_id=eq.${CHILD}` },
    ]);
    fake.deliver({ eventType: "UPDATE", new: row("active_investigations", 4), old: {} });
    fake.deliver({ eventType: "INSERT", new: row("active_hypotheses", 4), old: {} });
    fake.deliver({ eventType: "DELETE", new: {}, old: { child_id: CHILD } });
    expect(rows).toHaveLength(2);
    for (const s of ["SUBSCRIBED", "CHANNEL_ERROR", "TIMED_OUT", "CLOSED", "SOMETHING_NEW"]) fake.status(s);
    expect(statuses).toEqual(["subscribed", "error", "error", "closed", "error"]);
    stop();
    expect(fake.raw.removeChannel).toHaveBeenCalledTimes(1);
  });
});

describe("projectionFeed", () => {
  it("builds a feed for a configured project without connecting", async () => {
    const { projectionFeed } = await import("./client");
    const feed = projectionFeed({ url: "https://example.supabase.co", anonKey: "public-anon-key" });
    expect(typeof feed.fetchSnapshot).toBe("function");
    expect(typeof feed.subscribe).toBe("function");
  }, 30_000); // a cold import of supabase-js can be slow on a loaded runner
});
