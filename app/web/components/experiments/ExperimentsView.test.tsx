import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import payload from "@/fixtures/synthetic-experiments.json";
import type { ApprovalCommand } from "@/lib/experiments/approval";
import { PHASES, parseExperimentsView } from "@/lib/experiments/model";
import { PHASE_LABELS } from "@/lib/experiments/present";
import type { ExperimentsSource } from "@/lib/experiments/source";
import { ExperimentsView } from "./ExperimentsView";

const view = parseExperimentsView(payload);
const ready: ExperimentsSource = { status: "ready", view };

const card = (container: HTMLElement, selector: string) =>
  container.querySelector<HTMLElement>(`article[data-experiment-id]${selector}`)!;
const greenAwaiting = view.experiments.find((e) => e.phase === "AWAITING_APPROVAL" && e.safety_class === "GREEN")!;

describe("ExperimentsView across the lifecycle", () => {
  it("renders every lifecycle stage, each in words", () => {
    const { container } = render(<ExperimentsView source={ready} />);
    for (const phase of PHASES) {
      const article = card(container, `[data-phase="${phase}"]`);
      expect(article, phase).not.toBeNull();
      expect(article.querySelector("[data-phase-label]")).toHaveTextContent(PHASE_LABELS[phase].term);
      expect(article).toHaveTextContent(PHASE_LABELS[phase].description);
    }
  });

  it("shows intervention, risk, reversibility, approval, stage, outcomes and promotion for every experiment", () => {
    const { container } = render(<ExperimentsView source={ready} />);
    const articles = [...container.querySelectorAll<HTMLElement>("article[data-experiment-id]")];
    expect(articles).toHaveLength(view.experiments.length);
    for (const article of articles) {
      const e = view.experiments.find((x) => x.experiment_id === article.dataset.experimentId)!;
      expect(within(article).getByRole("heading", { level: 3 })).toHaveTextContent(e.intervention.description);
      expect(article.querySelector("[data-safety-label]")!.textContent).toMatch(/^Risk: /);
      expect(article).toHaveTextContent(e.intervention.reversible ? "Yes. It can be stopped and undone" : "No.");
      for (const name of ["Risk", "Approval", "Timeline", "Outcomes", "Promotion result"]) {
        expect(within(article).getByRole("region", { name })).toBeInTheDocument();
      }
      for (const o of e.outcomes) expect(article).toHaveTextContent(o.summary);
    }
  });

  it("shows both promotion results with their reasons", () => {
    const { container } = render(<ExperimentsView source={ready} />);
    expect(container.querySelector('[data-promotion="granted"]')).toHaveTextContent(
      "Promoted: the explanation is now held as a tested hypothesis.",
    );
    const denied = container.querySelector('[data-promotion="denied"]')!.closest("section")!;
    expect(denied).toHaveTextContent("An outcome contradicted the explanation.");
    expect(denied).toHaveTextContent("CONTRADICTING_OUTCOME");
  });

  it("puts what needs the parent first", () => {
    render(<ExperimentsView source={ready} />);
    const groups = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(groups[0]).toMatch(/^Waiting for your decision/);
  });

  it("states every state in words, not by colour", () => {
    const { container } = render(<ExperimentsView source={ready} />);
    for (const article of container.querySelectorAll<HTMLElement>("article[data-experiment-id]")) {
      expect(article.querySelector("[data-phase-label]")!.textContent!.length).toBeGreaterThan(3);
      expect(article.querySelector("[data-safety-label]")!.textContent!.length).toBeGreaterThan(6);
    }
    expect(container).not.toHaveTextContent(/%|confidence|score/i);
    expect(container.innerHTML).not.toMatch(/chd_|act_/);
  });
});

describe("RED interventions", () => {
  it("are visibly blocked and offer no way to approve", async () => {
    const decide = vi.fn();
    const { container } = render(<ExperimentsView source={ready} decide={decide} />);
    const red = card(container, '[data-safety="RED"]');
    expect(red.dataset.phase).toBe("BLOCKED");
    expect(red.querySelector("[data-safety-label]")).toHaveTextContent("Risk: Not allowed");
    expect(red.querySelector('[data-decision="not-approvable"]')).toHaveTextContent("This cannot be approved");
    expect(within(red).getByRole("list", { name: "Why it is blocked" })).toHaveTextContent("RED_FAIL_CLOSED");
    expect(within(red).queryAllByRole("button")).toEqual([]);
    expect(decide).not.toHaveBeenCalled();
  });
});

describe("deciding", () => {
  it("offers no decision while no transport is connected", () => {
    const { container } = render(<ExperimentsView source={ready} decide={null} />);
    for (const article of container.querySelectorAll<HTMLElement>('article[data-phase="AWAITING_APPROVAL"]')) {
      expect(article.querySelector('[data-decision="unconnected"]')).not.toBeNull();
      expect(within(article).queryAllByRole("button")).toEqual([]);
    }
  });

  it("sends exactly the shown request to the kernel and shows its answer, not its own", async () => {
    const user = userEvent.setup();
    const sent: ApprovalCommand[] = [];
    const decide = vi.fn(async (command: ApprovalCommand) => {
      sent.push(command);
      return { outcome: "APPROVAL_GRANTED", reason_codes: [] };
    });
    const { container } = render(<ExperimentsView source={ready} decide={decide} />);
    const article = container.querySelector<HTMLElement>(`[data-experiment-id="${greenAwaiting.experiment_id}"]`)!;

    await user.click(within(article).getByRole("button", { name: "Approve" }));
    expect(decide).not.toHaveBeenCalled(); // a confirmation comes first
    const confirm = within(article).getByRole("button", { name: "Yes, approve" });
    await waitFor(() => expect(confirm).toHaveFocus());
    await user.click(confirm);

    expect(decide).toHaveBeenCalledTimes(1);
    expect(sent[0]).toMatchObject({
      approval_request_id: greenAwaiting.approval!.approval_request_id,
      decision: "APPROVE",
      shown_intervention_digest: greenAwaiting.approval!.intervention_digest,
      shown_safety_class: "GREEN",
    });
    expect(await within(article).findByRole("status")).toHaveTextContent("Serene recorded your approval.");
    // The stage changes only when Serene's record does.
    expect(article.dataset.phase).toBe("AWAITING_APPROVAL");
    expect(article.querySelector("[data-phase-label]")).toHaveTextContent("Waiting for your decision");
  });

  it("declines through the same path", async () => {
    const user = userEvent.setup();
    const decide = vi.fn(async (_command: ApprovalCommand) => ({ outcome: "APPROVAL_REJECTED", reason_codes: [] }));
    const { container } = render(<ExperimentsView source={ready} decide={decide} />);
    const article = container.querySelector<HTMLElement>(`[data-experiment-id="${greenAwaiting.experiment_id}"]`)!;
    await user.click(within(article).getByRole("button", { name: "Decline" }));
    await user.click(within(article).getByRole("button", { name: "Yes, decline" }));
    expect(decide.mock.calls[0][0]).toMatchObject({ decision: "DECLINE" });
    expect(await within(article).findByText(/recorded your decision to decline/)).toBeInTheDocument();
  });

  it("shows a refusal with the kernel's reasons", async () => {
    const user = userEvent.setup();
    const decide = vi.fn(async () => ({ outcome: "REFUSED", reason_codes: ["AMBER_DELIBERATION_TOO_SHORT"] }));
    const { container } = render(<ExperimentsView source={ready} decide={decide} />);
    const article = container.querySelector<HTMLElement>(`[data-experiment-id="${greenAwaiting.experiment_id}"]`)!;
    await user.click(within(article).getByRole("button", { name: "Approve" }));
    await user.click(within(article).getByRole("button", { name: "Yes, approve" }));
    const reasons = await within(article).findByRole("list", { name: "Why it was not recorded" });
    expect(reasons).toHaveTextContent("cannot be approved this soon");
    expect(article).toHaveTextContent("Serene did not record this decision.");
  });

  it.each([
    ["an unreadable answer", async () => ({ outcome: "PROBABLY_FINE" })],
    ["a failed request", async () => Promise.reject(new Error("offline"))],
  ])("never shows success for %s", async (_name, answer) => {
    const user = userEvent.setup();
    const { container } = render(<ExperimentsView source={ready} decide={answer} />);
    const article = container.querySelector<HTMLElement>(`[data-experiment-id="${greenAwaiting.experiment_id}"]`)!;
    await user.click(within(article).getByRole("button", { name: "Approve" }));
    await user.click(within(article).getByRole("button", { name: "Yes, approve" }));
    expect(await within(article).findByText(/could not be confirmed/)).toBeInTheDocument();
    expect(article).not.toHaveTextContent("recorded your approval");
  });
});

describe("ExperimentsView states", () => {
  it("is honest when nothing is connected", () => {
    render(<ExperimentsView source={{ status: "unconnected" }} />);
    expect(screen.getByRole("heading", { name: "No experiments proposed" })).toBeInTheDocument();
  });

  it("announces loading", () => {
    render(<ExperimentsView source={{ status: "loading" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading experiments");
  });

  it("fails closed", () => {
    render(<ExperimentsView source={{ status: "error", reason: "x" }} />);
    expect(screen.getByRole("heading", { name: "Experiments couldn’t be shown" })).toBeInTheDocument();
  });

  it("says so when a connected record has no experiments", () => {
    render(<ExperimentsView source={{ status: "ready", view: { ...view, experiments: [] } }} />);
    expect(screen.getByRole("heading", { name: "No experiments proposed yet" })).toBeInTheDocument();
  });
});
