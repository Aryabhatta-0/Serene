import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { supabaseConfig } from "@/lib/projections/config";
import type { ProjectionFeed } from "@/lib/projections/sync";
import { CHILD, FakeFeed, row } from "@/lib/projections/testing";
import { useProjections } from "@/lib/projections/useProjections";
import { ProjectionStatus } from "./ProjectionStatus";

// A tiny consumer, the way a surface uses the hook: it shows the open
// investigations straight from the projection.
function Investigations({ feed }: { feed: ProjectionFeed | null }) {
  const state = useProjections(feed, feed ? CHILD : null);
  const ids =
    state.status === "live" || state.status === "reconnecting"
      ? Object.keys(state.projections.active_investigations?.state ?? {})
      : [];
  return (
    <>
      <ProjectionStatus state={state} />
      <ul aria-label="Open investigations">
        {ids.map((id) => (
          <li key={id}>{id}</li>
        ))}
      </ul>
    </>
  );
}

describe("the UI and live projection state", () => {
  it("stays unconnected with no feed", () => {
    render(<Investigations feed={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Not connected to a family record.");
  });

  it("updates the UI when a projection changes, and says when it is not current", async () => {
    const feed = new FakeFeed();
    feed.write(row("active_investigations", 3, {}), { deliver: false });
    render(<Investigations feed={feed} />);
    expect(screen.getByRole("status")).toHaveTextContent("Connecting to Serene…");

    await act(async () => feed.setStatus("subscribed"));
    expect(screen.getByRole("status")).toHaveTextContent("Live: up to date with Serene’s record.");
    expect(screen.queryAllByRole("listitem")).toEqual([]);

    await act(async () => feed.write(row("active_investigations", 4, { inv_1: { status: "OPEN" } })));
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["inv_1"]);

    await act(async () => feed.setStatus("error"));
    expect(screen.getByRole("status")).toHaveTextContent("Reconnecting. Showing what Serene last sent");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);

    feed.write(row("active_investigations", 6, { inv_1: {}, inv_2: {} }), { deliver: false });
    await act(async () => feed.setStatus("subscribed"));
    expect(screen.getByRole("status")).toHaveTextContent("Live");
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["inv_1", "inv_2"]);
  });
});

describe("supabaseConfig", () => {
  it("is absent unless both public values are set", () => {
    expect(supabaseConfig({})).toBeNull();
    expect(supabaseConfig({ NEXT_PUBLIC_SUPABASE_URL: "https://x.supabase.co" })).toBeNull();
    expect(supabaseConfig({ NEXT_PUBLIC_SUPABASE_URL: "ftp://x", NEXT_PUBLIC_SUPABASE_ANON_KEY: "k" })).toBeNull();
    expect(
      supabaseConfig({ NEXT_PUBLIC_SUPABASE_URL: "https://x.supabase.co", NEXT_PUBLIC_SUPABASE_ANON_KEY: "k" }),
    ).toEqual({ url: "https://x.supabase.co", anonKey: "k" });
  });
});
