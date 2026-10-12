import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FamilyRecordProvider } from "@/components/session/FamilyRecord";
import payload from "@/fixtures/synthetic-experiments.json";
import { FakeBackend } from "@/lib/auth/testing";
import { UNCONNECTED } from "@/lib/experiments/source";
import { FakeFeed, row } from "@/lib/projections/testing";
import { LiveExperiments } from "./LiveExperiments";

// The Experiments surface on the signed-in family record: the kernel's
// `experiments` projection over the #33 sync path, and the real transport
// (#84) for the chosen child only. The stage changes only when the projection
// does, never on the kernel's answer alone. All data is synthetic kernel output.
const PARENT = { email: "parent@example.org", password: "fake-synthetic-only", userId: "00000000-0000-4000-8000-000000000001" };
const CHILD = `chd_${"a".repeat(32)}`;
const green = payload.experiments.find((e) => e.phase === "AWAITING_APPROVAL" && e.safety_class === "GREEN")!;
const red = payload.experiments.find((e) => e.safety_class === "RED")!;

/** What the kernel publishes once it has recorded the approval. */
function approved() {
  const next = structuredClone(payload);
  const e = next.experiments.find((x) => x.experiment_id === green.experiment_id)!;
  e.phase = "APPROVED";
  Object.assign(e.approval!, { state: "GRANTED", decided_at: "2026-09-07T12:00:00Z", decided_via: "WEB_APP", decision_open: false });
  return next;
}

async function setup(rows = [row("experiments", 40, payload as never, CHILD)]) {
  const feed = new FakeFeed();
  for (const r of rows) feed.write(r, { deliver: false });
  const backend = new FakeBackend(feed, [PARENT], { [PARENT.userId]: [CHILD] });
  render(
    <FamilyRecordProvider backend={backend}>
      <LiveExperiments unconnected={UNCONNECTED} />
    </FamilyRecordProvider>,
  );
  await act(async () => {});
  const signIn = async () => {
    await act(async () => void (await backend.signIn(PARENT.email, PARENT.password)));
    await act(async () => feed.setStatus("subscribed"));
  };
  return { feed, backend, signIn };
}

const article = (id: string) => document.querySelector<HTMLElement>(`article[data-experiment-id="${id}"]`);

afterEach(() => vi.unstubAllGlobals());

describe("LiveExperiments", () => {
  it("signed out, shows the honest unconnected state and nothing to decide", async () => {
    const { feed } = await setup();
    expect(screen.getByText("No experiments proposed")).toBeInTheDocument();
    expect(article(green.experiment_id)).toBeNull();
    expect(feed.subscribers).toBe(0);
  });

  it("signed in, shows the child's experiments live from the projection", async () => {
    const { signIn } = await setup();
    await signIn();
    expect(article(green.experiment_id)).toHaveAttribute("data-phase", "AWAITING_APPROVAL");
    expect(document.querySelector('[data-sync="live"]')).not.toBeNull();
    expect(within(article(red.experiment_id)!).queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("sends the decision for the chosen child, and the stage moves only when the projection does", async () => {
    const send = vi.fn(
      async (_url: string, _init: RequestInit) =>
        new Response(JSON.stringify({ outcome: "APPROVAL_GRANTED", event_ids: [], reason_codes: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", send);
    const { feed, signIn } = await setup();
    await signIn();
    const card = article(green.experiment_id)!;
    const user = userEvent.setup();
    await user.click(within(card).getByRole("button", { name: "Approve" }));
    await user.click(within(card).getByRole("button", { name: "Yes, approve" }));
    expect(await within(card).findByText(/Serene recorded your approval/)).toBeInTheDocument();

    const [url, init] = send.mock.calls[0];
    expect(url).toBe("/api/approvals");
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer fake-access.${PARENT.userId}.token`);
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ child_id: CHILD, command: expect.objectContaining({ decision: "APPROVE" }) });
    expect(body.command.approval_request_id).toBe(green.approval!.approval_request_id);
    // The kernel answered, but its record has not moved yet: neither has the page.
    expect(article(green.experiment_id)).toHaveAttribute("data-phase", "AWAITING_APPROVAL");

    // The kernel's projection publish arrives over Realtime.
    await act(async () => feed.write(row("experiments", 41, approved() as never, CHILD)));
    expect(article(green.experiment_id)).toHaveAttribute("data-phase", "APPROVED");
  });

  it("a child with nothing proposed says so", async () => {
    const empty = await setup([row("experiments", 3, {}, CHILD)]);
    await empty.signIn();
    expect(screen.getByText("No experiments proposed yet")).toBeInTheDocument();
  });

  it("a missing projection row is an error, not an empty list", async () => {
    const missing = await setup([row("investigations", 3, {}, CHILD)]);
    await missing.signIn();
    expect(screen.getByText("Experiments couldn’t be shown")).toBeInTheDocument();
  });
});
