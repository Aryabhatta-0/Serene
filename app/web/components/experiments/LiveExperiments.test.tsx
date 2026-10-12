import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FamilyRecordProvider } from "@/components/session/FamilyRecord";
import payload from "@/fixtures/synthetic-experiments.json";
import { FakeBackend } from "@/lib/auth/testing";
import { parseExperimentsView } from "@/lib/experiments/model";
import { FakeFeed } from "@/lib/projections/testing";
import { LiveExperiments } from "./LiveExperiments";

// The Experiments surface on the real transport (Issue #84): only a signed-in
// parent with a child chosen can decide, the request carries that child and
// the session token, and the stage shown never changes on the answer alone.
const view = parseExperimentsView(payload);
const PARENT = { email: "parent@example.org", password: "fake-synthetic-only", userId: "00000000-0000-4000-8000-000000000001" };
const CHILD = `chd_${"a".repeat(32)}`;
const green = view.experiments.find((e) => e.phase === "AWAITING_APPROVAL" && e.safety_class === "GREEN")!;

function setup() {
  const backend = new FakeBackend(new FakeFeed(), [PARENT], { [PARENT.userId]: [CHILD] });
  const view_ = render(
    <FamilyRecordProvider backend={backend}>
      <LiveExperiments source={{ status: "ready", view }} />
    </FamilyRecordProvider>,
  );
  return { backend, ...view_ };
}

const article = (id: string) => document.querySelector<HTMLElement>(`article[data-experiment-id="${id}"]`)!;

afterEach(() => vi.unstubAllGlobals());

describe("LiveExperiments", () => {
  it("offers no decision while signed out", async () => {
    setup();
    await act(async () => {});
    expect(article(green.experiment_id).querySelector('[data-decision="unconnected"]')).not.toBeNull();
  });

  it("sends a signed-in parent's decision for the chosen child, and waits for the record to change", async () => {
    const send = vi.fn(
      async (_url: string, _init: RequestInit) =>
        new Response(JSON.stringify({ outcome: "APPROVAL_GRANTED", event_ids: [], reason_codes: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", send);
    const { backend } = setup();
    await act(async () => void (await backend.signIn(PARENT.email, PARENT.password)));
    const card = article(green.experiment_id);
    const user = userEvent.setup();
    await user.click(await within(card).findByRole("button", { name: "Approve" }));
    await user.click(within(card).getByRole("button", { name: "Yes, approve" }));
    expect(await within(card).findByText(/Serene recorded your approval/)).toBeInTheDocument();

    const [url, init] = send.mock.calls[0];
    expect(url).toBe("/api/approvals");
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer fake-access.${PARENT.userId}.token`);
    const body = JSON.parse(init.body as string);
    expect(body.child_id).toBe(CHILD);
    expect(body.command.approval_request_id).toBe(green.approval!.approval_request_id);
    // No optimistic change: the stage is the one Serene's record still says.
    expect(card).toHaveAttribute("data-phase", "AWAITING_APPROVAL");
    expect(screen.getAllByText(/once Serene’s record updates/).length).toBeGreaterThan(0);
  });

  it("a RED experiment offers nothing to approve even when signed in", async () => {
    vi.stubGlobal("fetch", vi.fn());
    const { backend } = setup();
    await act(async () => void (await backend.signIn(PARENT.email, PARENT.password)));
    const red = view.experiments.find((e) => e.safety_class === "RED")!;
    expect(within(article(red.experiment_id)).queryByRole("button", { name: "Approve" })).toBeNull();
  });
});
