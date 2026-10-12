import { act, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import recorded from "@/fixtures/synthetic-investigation.json";
import { nextActionText, UNCERTAINTY_TEXT } from "@/lib/investigations/present";
import { FakeFeed, type Row } from "@/lib/projections/testing";
import { InvestigationSurface } from "./InvestigationSurface";

// The kernel-recorded rows (tests/investigation_view_fixture.py), fed through
// the same ProjectionSync path the live Realtime feed uses (#33).
const CHILD = recorded.snapshot[0].child_id;
const invRow = (rows: Row[]) => rows.find((r) => r.projection === "investigations")!;
const kernelView = (r: Row) => Object.values(r.state)[0] as any;

async function connected(mode: "today" | "all", rows: Row[] = recorded.snapshot as Row[]) {
  const feed = new FakeFeed();
  for (const r of rows) feed.write(r, { deliver: false });
  const view = render(<InvestigationSurface feed={feed} childId={CHILD} mode={mode} unconnected={<p>unconnected</p>} />);
  await act(async () => feed.setStatus("subscribed"));
  return { feed, ...view };
}

const block = (name: string) => document.querySelector<HTMLElement>(`[data-block="${name}"]`)!;

describe("an active investigation", () => {
  it("shows its state, hypotheses, missing evidence, source, verification, uncertainty and next action", async () => {
    await connected("today");
    const kernel = kernelView(invRow(recorded.snapshot as Row[]));
    const article = screen.getByRole("article");
    expect(article.querySelector("[data-phase-label]")).toHaveTextContent("Asking you");
    expect(within(article).getByRole("heading", { level: 2 })).toHaveTextContent(kernel.question);
    for (const h of kernel.hypotheses) expect(block("hypotheses")).toHaveTextContent(h.statement);
    expect(block("missing-evidence")).toHaveTextContent(kernel.evidence_requests[0].question);
    expect(block("missing-evidence").querySelector("[data-selected-source]")).toHaveTextContent(
      "Asking you one yes-or-no question",
    );
    expect(block("verification")).toHaveTextContent("No evidence has arrived for this question yet.");
    expect(block("uncertainty")).toBeInTheDocument();
    expect(block("next-action")).toBeInTheDocument();
  });

  it("shows uncertainty as the kernel stated it, never masked", async () => {
    await connected("today");
    const facts = kernelView(invRow(recorded.snapshot as Row[])).uncertainty as (keyof typeof UNCERTAINTY_TEXT)[];
    const shown = [...block("uncertainty").querySelectorAll("[data-uncertainty]")];
    expect(shown.map((li) => li.getAttribute("data-uncertainty"))).toEqual(facts);
    for (const li of shown) {
      expect(li).toHaveTextContent(UNCERTAINTY_TEXT[li.getAttribute("data-uncertainty") as keyof typeof UNCERTAINTY_TEXT]);
    }
    expect(document.body).not.toHaveTextContent(/%|confidence|probab|score/i);
  });
});

describe("the next action", () => {
  it("is exactly the kernel's policy output, at every recorded step", async () => {
    const { feed } = await connected("all");
    const steps = [invRow(recorded.snapshot as Row[]), ...(recorded.changes as Row[]).filter((r) => r.projection === "investigations")];
    for (const [i, step] of steps.entries()) {
      if (i > 0) await act(async () => feed.write(step));
      const kernel = kernelView(step).next_action;
      const shown = block("next-action").querySelector("[data-next-action]")!;
      expect(shown.getAttribute("data-next-action")).toBe(kernel.kind);
      expect(shown).toHaveTextContent(nextActionText(kernel).title);
      if (kernel.question) expect(block("next-action")).toHaveTextContent(kernel.question);
    }
  });

  it("follows whatever the policy says, with nothing hardcoded", async () => {
    const rows = structuredClone(recorded.snapshot) as Row[];
    const view = kernelView(invRow(rows));
    view.next_action = { ...view.next_action, kind: "CHOOSE_EVIDENCE", question: null, request_id: null, acquisition_mode: null };
    await connected("today", rows);
    expect(block("next-action").querySelector("[data-next-action]")).toHaveAttribute("data-next-action", "CHOOSE_EVIDENCE");
    expect(block("next-action")).not.toHaveTextContent("waiting for your answer");
  });
});

describe("live updates", () => {
  it("follows the projection as it changes, including verification", async () => {
    const { feed } = await connected("all");
    for (const change of recorded.changes as Row[]) await act(async () => feed.write(change));
    const article = screen.getByRole("article");
    expect(article).toHaveAttribute("data-phase", "COMPLETE");
    expect(block("verification").querySelector("[data-verification]")).toHaveTextContent("Checked and accepted");
    expect(block("next-action").querySelector("[data-next-action]")).toHaveAttribute("data-next-action", "NONE_COMPLETE");
    // Still not resolved between the explanations: that stays visible.
    expect(block("uncertainty")).toHaveTextContent(UNCERTAINTY_TEXT.COMPETING_EXPLANATIONS);
  });
});

describe("states", () => {
  it("shows the surface's own empty state while unconnected", () => {
    render(<InvestigationSurface feed={null} childId={null} mode="today" unconnected={<p>Nothing to review today</p>} />);
    expect(screen.getByText("Nothing to review today")).toBeInTheDocument();
  });

  it("says so when there are no investigations", async () => {
    const empty = (recorded.snapshot as Row[]).map((r) => (r.projection === "investigations" ? { ...r, state: {} } : r));
    await connected("all", empty);
    expect(screen.getByRole("heading", { name: "No open investigations" })).toBeInTheDocument();
  });

  it("fails closed on a projection that does not pass its checks", async () => {
    const bad = structuredClone(recorded.snapshot) as Row[];
    delete kernelView(invRow(bad)).next_action;
    await connected("all", bad);
    expect(screen.getByRole("heading", { name: "Serene’s state couldn’t be read" })).toBeInTheDocument();
    expect(document.querySelector("[data-next-action]")).toBeNull();
  });
});

describe("why it stopped", () => {
  it("explains every reason the kernel recorded for this investigation", async () => {
    const { feed } = await connected("all");
    for (const change of recorded.changes as Row[]) await act(async () => feed.write(change));
    const reasons = [...block("next-action").querySelectorAll("[data-reason-code]")];
    expect(reasons.length).toBeGreaterThan(0);
    for (const r of reasons) expect(r).toHaveAttribute("data-known", "true");
  });
});
