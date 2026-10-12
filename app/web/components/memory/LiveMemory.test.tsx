import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FamilyRecordProvider, useFamilyRecord } from "@/components/session/FamilyRecord";
import payload from "@/fixtures/synthetic-memory-dream.json";
import { FakeBackend } from "@/lib/auth/testing";
import { CHILD, OTHER_CHILD, FakeFeed, row } from "@/lib/projections/testing";
import { LiveMemory } from "./LiveMemory";

const PARENT = { email: "parent@example.org", password: "fake-synthetic-only", userId: "00000000-0000-4000-8000-000000000001" };
function SelectChild() {
  const { selectChild } = useFamilyRecord();
  return <button onClick={() => selectChild(OTHER_CHILD)}>Other child</button>;
}
function setup(children = [CHILD]) {
  const feed = new FakeFeed();
  feed.table = [row("memory_review", 1, {}), row("memory_dream", 1, payload)];
  const backend = new FakeBackend(feed, [PARENT], { [PARENT.userId]: children });
  render(<FamilyRecordProvider backend={backend}><SelectChild /><LiveMemory /></FamilyRecordProvider>);
  return { feed, backend };
}
async function connect(backend: FakeBackend, feed: FakeFeed) {
  await act(async () => void (await backend.signIn(PARENT.email, PARENT.password)));
  await act(async () => feed.setStatus("subscribed"));
}

describe("LiveMemory", () => {
  it("requires a session and selected child", async () => {
    const { backend, feed } = setup([]);
    await act(async () => {});
    expect(screen.getByText("No memories yet")).toBeInTheDocument();
    await connect(backend, feed);
    expect(screen.queryByText(payload.memories[0].title)).toBeNull();
    expect(feed.subscribers).toBe(0);
  });

  it("shows loading, live memory, the exact revision and refusal reasons", async () => {
    const { backend, feed } = setup();
    feed.holdSnapshots = true;
    await act(async () => void (await backend.signIn(PARENT.email, PARENT.password)));
    expect(screen.getByText("Loading memory")).toBeInTheDocument();
    feed.holdSnapshots = false;
    await act(async () => feed.release());
    await act(async () => feed.setStatus("subscribed"));
    expect(screen.getByRole("heading", { name: payload.memories[0].title, level: 3 })).toBeInTheDocument();
    expect(screen.getByText(payload.memory_head)).toBeInTheDocument();
    expect(document.querySelector('[data-status="REJECTED"]')).toHaveTextContent("Not enough evidence");
  });

  it("changes only on projection delivery and resyncs after disconnect", async () => {
    const { backend, feed } = setup();
    await connect(backend, feed);
    const updated = structuredClone(payload);
    updated.memories[0].title = "New reviewed memory";
    feed.write(row("memory_dream", 2, updated), { deliver: false });
    expect(screen.queryByText("New reviewed memory")).toBeNull();
    await act(async () => feed.emit(row("memory_dream", 2, updated)));
    expect(screen.getByText("New reviewed memory")).toBeInTheDocument();
    await act(async () => feed.setStatus("closed"));
    expect(screen.getByText(/Reconnecting/)).toBeInTheDocument();
    expect(screen.getByText("New reviewed memory")).toBeInTheDocument();
    feed.table = [row("memory_review", 3, {})];
    await act(async () => feed.setStatus("subscribed"));
    expect(screen.queryByText("New reviewed memory")).toBeNull();
    expect(screen.getByText("Nothing remembered yet")).toBeInTheDocument();
  });

  it("discards memory on child switches and sign-out, rejects cross-child delivery", async () => {
    const { backend, feed } = setup([CHILD, OTHER_CHILD]);
    await connect(backend, feed);
    await userEvent.click(screen.getByRole("button", { name: "Other child" }));
    expect(screen.queryByText(payload.memories[0].title)).toBeNull();
    await act(async () => feed.setStatus("subscribed"));
    await act(async () => feed.emit(row("memory_dream", 9, payload, CHILD)));
    expect(screen.queryByText(payload.memories[0].title)).toBeNull();
    await act(async () => backend.signOut());
    expect(feed.subscribers).toBe(0);
    expect(screen.getByText("No memories yet")).toBeInTheDocument();
  });

  it("fails honestly for invalid or missing published data", async () => {
    const { backend, feed } = setup();
    feed.table = [row("memory_dream", 1, { memories: [] })];
    await connect(backend, feed);
    expect(screen.getByText("Memory couldn’t be shown")).toBeInTheDocument();
    expect(screen.queryByText(payload.memories[0].title)).toBeNull();
  });
});
