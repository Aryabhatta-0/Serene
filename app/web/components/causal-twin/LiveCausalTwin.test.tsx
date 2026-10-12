import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FamilyRecordProvider, useFamilyRecord } from "@/components/session/FamilyRecord";
import { RecordControl } from "@/components/session/RecordControl";
import payload from "@/fixtures/synthetic-causal-twin-web.json";
import { FakeBackend } from "@/lib/auth/testing";
import { FakeFeed, OTHER_CHILD, row } from "@/lib/projections/testing";
import { LiveCausalTwin } from "./LiveCausalTwin";

// The Causal Twin on the signed-in family record: the selected child's
// `causal_twin` projection row, and nothing else. The fixture is kernel
// output (tests/twin_provenance_fixture.py), the row the publisher writes.
const PARENT = { email: "parent@example.org", password: "fake-synthetic-only", userId: "00000000-0000-4000-8000-000000000001" };
const CHILD = `chd_${"a".repeat(32)}`;
const EDGES = payload.edges.map((e) => e.edge_id);
const STATEMENT = (id: string) => payload.edges.find((e) => e.edge_id === id)!.relationship;
const replaced = payload.edges.find((e) => e.status === "SUPERSEDED")!;

/** The same twin without its replaced link: what the record held one append earlier. */
function earlier(): Record<string, unknown> {
  const twin = structuredClone(payload);
  twin.edges = twin.edges.filter((e) => e.edge_id !== replaced.edge_id);
  twin.provenance.edges = twin.provenance.edges.filter((e) => e.edge_id !== replaced.edge_id);
  const used = new Set(twin.edges.flatMap((e) => [e.from_node, e.to_node]));
  twin.nodes = twin.nodes.filter((n) => used.has(n.node_id));
  return twin;
}

function SelectChild() {
  const { selectChild } = useFamilyRecord();
  return <button onClick={() => selectChild(OTHER_CHILD)}>Other child</button>;
}

function setup(children = [CHILD], state: Record<string, unknown> = payload) {
  const feed = new FakeFeed();
  feed.table = [row("causal_twin", 5, state), row("experiments", 5, {})];
  const backend = new FakeBackend(feed, [PARENT], { [PARENT.userId]: children });
  const view = render(
    <FamilyRecordProvider backend={backend}>
      <RecordControl next="/causal-twin" />
      <SelectChild />
      <LiveCausalTwin />
    </FamilyRecordProvider>,
  );
  return { backend, feed, ...view };
}

async function connect(backend: FakeBackend, feed: FakeFeed) {
  await act(async () => void (await backend.signIn(PARENT.email, PARENT.password)));
  await act(async () => feed.setStatus("subscribed"));
}

const status = () => document.querySelector("[data-sync]")?.getAttribute("data-sync") ?? null;
const listButton = (id: string) =>
  document.querySelector<HTMLButtonElement>(`section button[data-edge-id="${id}"]:not(.react-flow *)`);
const panel = () => screen.queryByRole("complementary", { name: "Selected link" });
/** The provenance of a chosen link (the panel itself stays, with a hint, when none is). */
const opened = () => document.querySelector("[data-provenance-for]");
const shownEdges = () =>
  [...document.querySelectorAll("section button[data-edge-id]:not(.react-flow *)")].map((b) => b.getAttribute("data-edge-id"));

describe("LiveCausalTwin", () => {
  it("draws nothing while signed out", async () => {
    setup();
    await act(async () => {});
    expect(screen.getByText("No links to draw yet")).toBeInTheDocument();
    for (const id of EDGES) expect(document.body).not.toHaveTextContent(STATEMENT(id));
  });

  it("loads, then draws the live twin, and the edge panel shows its complete provenance", async () => {
    const { backend, feed } = setup();
    await act(async () => void (await backend.signIn(PARENT.email, PARENT.password)));
    expect(status()).toBe("connecting");
    expect(screen.getByText("Loading the Causal Twin")).toBeInTheDocument();
    await act(async () => feed.setStatus("subscribed"));
    expect(status()).toBe("live");
    expect(shownEdges().sort()).toEqual([...EDGES].sort());
    for (const id of EDGES) {
      await userEvent.click(listButton(id)!);
      const root = panel()!.querySelector(`[data-provenance-for="${id}"]`)!;
      expect(root).toHaveAttribute("data-provenance", "full");
      expect(root.querySelector("[data-field=complete]")).toHaveTextContent("Complete");
      const detail = payload.provenance.edges.find((e) => e.edge_id === id)!;
      for (const x of detail.experiments) {
        const card = root.querySelector(`[data-experiment-id="${x.experiment_id}"]`)!;
        for (const o of x.outcomes) expect(card.querySelector(`[data-outcome-id="${o.outcome_id}"]`)).toHaveTextContent(o.summary);
      }
      for (const c of detail.counterevidence) expect(root.querySelector(`[data-entity-id="${c.entity_id}"]`)).not.toBeNull();
      expect(panel()).not.toHaveTextContent(/\b(chd|act|src)_[0-9a-f]{32}\b/);
    }
    // The last link chosen is the replaced one: its supersession reason is shown.
    expect(within(panel()!).getAllByText(/Narrowed to pickups after the posted pickup window/).length).toBeGreaterThan(0);
  }, 20_000);

  it("republishes on a live append: only a newer row changes the map", async () => {
    const { backend, feed } = setup([CHILD], earlier());
    await connect(backend, feed);
    expect(shownEdges()).not.toContain(replaced.edge_id);
    await act(async () => feed.emit(row("causal_twin", 4, payload))); // older: ignored
    expect(shownEdges()).not.toContain(replaced.edge_id);
    await act(async () => feed.write(row("causal_twin", 6, payload)));
    expect(shownEdges()).toContain(replaced.edge_id);
    await userEvent.click(listButton(replaced.edge_id)!);
    expect(panel()!.querySelector(`[data-provenance-for="${replaced.edge_id}"]`)).toHaveAttribute("data-provenance", "full");
  });

  it("keeps the last twin while reconnecting, then resyncs from a fresh snapshot", async () => {
    const { backend, feed } = setup([CHILD], earlier());
    await connect(backend, feed);
    await act(async () => feed.setStatus("closed"));
    expect(status()).toBe("reconnecting");
    expect(screen.getByText(/Reconnecting/)).toBeInTheDocument();
    expect(shownEdges()).toHaveLength(EDGES.length - 1);
    // Appended while disconnected: never delivered, picked up by the resync.
    feed.write(row("causal_twin", 7, payload), { deliver: false });
    await act(async () => feed.setStatus("subscribed"));
    expect(status()).toBe("live");
    expect(shownEdges().sort()).toEqual([...EDGES].sort());
  });

  it("discards the previous child's twin and open panel the moment the child changes", async () => {
    const { backend, feed } = setup([CHILD, OTHER_CHILD]);
    // The other child's record holds a different twin: one link fewer.
    feed.table.push(row("causal_twin", 3, earlier(), OTHER_CHILD));
    await connect(backend, feed);
    await userEvent.click(listButton(EDGES[0])!);
    expect(opened()).not.toBeNull();
    feed.holdSnapshots = true;
    await userEvent.click(screen.getByRole("button", { name: "Other child" }));
    // Before anything about the other child has arrived, nothing of the first remains.
    expect(opened()).toBeNull();
    expect(shownEdges()).toEqual([]);
    for (const id of EDGES) expect(document.body).not.toHaveTextContent(STATEMENT(id));
    // A late change for the first child is never shown under the second.
    await act(async () => feed.emit(row("causal_twin", 9, payload)));
    await act(async () => feed.setStatus("subscribed"));
    expect(shownEdges()).toEqual([]);
    await act(async () => feed.release());
    expect(status()).toBe("live");
    expect(shownEdges()).toHaveLength(EDGES.length - 1);
    expect(shownEdges()).not.toContain(replaced.edge_id);
    expect(opened()).toBeNull();
  }, 20_000);

  it("shows the empty map before any hypothesis, and fails closed on a bad or missing row", async () => {
    const empty = setup([CHILD], {});
    await connect(empty.backend, empty.feed);
    expect(screen.getByText("No links recorded yet")).toBeInTheDocument();
    empty.unmount();

    const bad = setup([CHILD], { version: "causal-twin-web/1", edges: [] });
    await connect(bad.backend, bad.feed);
    expect(screen.getByText("The map couldn’t be drawn")).toBeInTheDocument();
    bad.unmount();

    const leaky = setup([CHILD], { ...payload, child_id: CHILD });
    await connect(leaky.backend, leaky.feed);
    expect(screen.getByText("The map couldn’t be drawn")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(STATEMENT(EDGES[0]));
    leaky.unmount();

    const missing = setup();
    missing.feed.table = [row("experiments", 5, {})];
    await connect(missing.backend, missing.feed);
    expect(screen.getByText("The map couldn’t be drawn")).toBeInTheDocument();
  });

  it("drops the twin when the session ends, and unsubscribes", async () => {
    const { backend, feed } = setup();
    await connect(backend, feed);
    expect(shownEdges().length).toBe(EDGES.length);
    await act(async () => backend.expire());
    expect(screen.getByText("Your session ended")).toBeInTheDocument();
    expect(shownEdges()).toEqual([]);
    for (const id of EDGES) expect(document.body).not.toHaveTextContent(STATEMENT(id));
    expect(feed.subscribers).toBe(0);
  });
});
