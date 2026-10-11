import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-memory-dream.json";
import { parseMemoryDreamView } from "@/lib/memory/model";
import { memorySourceFrom, type MemorySource } from "@/lib/memory/source";
import { MemoryView } from "./MemoryView";

const view = parseMemoryDreamView(payload);
const ready: MemorySource = { status: "ready", view };

function renderView(source: MemorySource = ready) {
  return render(<MemoryView source={source} />);
}

describe("MemoryView with a fixture Dream run", () => {
  it("shows the kept memory with its scope, dates and level", () => {
    renderView();
    const memory = screen.getByRole("article", { name: "A five-minute heads-up helps weekday pickups" });
    expect(memory).toHaveTextContent(
      "On weekday daycare pickups, a five-minute heads-up before leaving went calmly.",
    );
    expect(memory).toHaveTextContent("Level 5 of 5: Contextual learning");
    expect(memory).toHaveTextContent("Daycare pickup, Weekday evening");
    expect(within(memory).getAllByRole("time").map((t) => t.getAttribute("datetime"))).toEqual([
      view.memories[0].valid_from,
      view.memories[0].review_after,
    ]);
  });

  it("shows accepted and rejected patches, each in words", () => {
    const { container } = renderView();
    const kept = container.querySelectorAll('[data-patch-id][data-status="COMMITTED"]');
    const refused = container.querySelectorAll('[data-patch-id][data-status="REJECTED"]');
    const waiting = container.querySelectorAll('[data-patch-id][data-status="PROPOSED"]');
    expect(kept).toHaveLength(1);
    expect(refused).toHaveLength(1);
    expect(waiting).toHaveLength(2);
    expect(kept[0]).toHaveTextContent("Kept");
    expect(kept[0]).toHaveTextContent("A five-minute heads-up helps weekday pickups");
    expect(refused[0]).toHaveTextContent("Refused");
    expect(refused[0]).toHaveTextContent("Needs a warning before every transition");
    for (const patch of waiting) expect(patch).toHaveTextContent("Awaiting review");
    // Every patch in the view is shown exactly once.
    const shown = [...container.querySelectorAll("[data-patch-id]")].map((el) => el.getAttribute("data-patch-id"));
    expect(shown.sort()).toEqual(view.patches.map((p) => p.patch_id).sort());
  });

  it("shows a reason for every rejected patch", () => {
    const { container } = renderView();
    const refused = [...container.querySelectorAll('[data-patch-id][data-status="REJECTED"]')];
    expect(refused.length).toBeGreaterThan(0);
    for (const patch of refused) {
      const id = patch.getAttribute("data-patch-id");
      const recorded = view.patches.find((p) => p.patch_id === id)!.rejection_reasons;
      const reasons = within(patch as HTMLElement).getByRole("list", { name: "Reasons it was refused" });
      const items = within(reasons).getAllByRole("listitem");
      expect(items.map((li) => li.getAttribute("data-reason-code"))).toEqual(recorded);
      for (const item of items) {
        expect(item.querySelector("span")!.textContent!.length).toBeGreaterThan(10);
      }
    }
    expect(refused[0]).toHaveTextContent(
      "Not enough evidence: it rests on an observation, and this kind of memory needs at least a pattern.",
    );
    expect(refused[0]).toHaveTextContent("INSUFFICIENT_EVIDENCE:OBSERVATION_BELOW_PATTERN");
  });

  it("groups each Dream run's proposals, newest run first, and lists its steps", () => {
    const { container } = renderView();
    const runs = [...container.querySelectorAll("[data-run-id]")];
    expect(runs.map((r) => r.getAttribute("data-run-id"))).toEqual(view.dream_runs.map((r) => r.run_id));
    const oldest = runs[1] as HTMLElement;
    expect(within(oldest).getByRole("list", { name: "Steps of this run" }).children).toHaveLength(6);
    expect(within(oldest).getByRole("region", { name: "Kept from this run" })).toHaveTextContent("(1)");
    expect(within(oldest).getByRole("region", { name: "Refused from this run" })).toHaveTextContent("(1)");
    expect(within(oldest).getByRole("region", { name: "Awaiting review from this run" })).toHaveTextContent(
      "Nothing from this run is waiting.",
    );
  });

  it("links every memory to its provenance, and every link resolves", () => {
    const { container } = renderView();
    const links = [...container.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')];
    expect(links.length).toBeGreaterThan(10);
    for (const link of links) {
      const target = container.querySelector(`[id="${link.getAttribute("href")!.slice(1)}"]`);
      expect(target, link.getAttribute("href")!).not.toBeNull();
    }

    const memory = view.memories[0];
    const article = container.querySelector(`[data-memory-path="${memory.path}"]`) as HTMLElement;
    // The change that wrote it: a kept patch whose commit is this revision.
    const keptBy = article.querySelector<HTMLAnchorElement>("a[data-written-by]")!;
    const patch = container.querySelector(keptBy.getAttribute("href")!)!;
    expect(patch.getAttribute("data-status")).toBe("COMMITTED");
    expect(patch.getAttribute("data-patch-id")).toBe(memory.written_by);
    // And back again.
    const back = within(patch as HTMLElement).getByRole("link", { name: "See the memory" });
    expect(back.getAttribute("href")).toBe(`#${article.id}`);

    // Each source is a node of the trail, and the trail ends at raw evidence.
    const sources = within(article).getByRole("list", { name: "Sources" });
    const sourceLinks = within(sources).getAllByRole("link");
    expect(sourceLinks).toHaveLength(memory.sources.length);
    const trail = within(article).getByRole("list", {
      name: "Evidence trail, from this memory down to raw evidence",
    });
    const nodes = within(trail).getAllByRole("listitem");
    expect(nodes).toHaveLength(memory.lineage.nodes.length);
    for (const link of sourceLinks) expect(trail.querySelector(link.getAttribute("href")!)).not.toBeNull();
    for (const raw of memory.lineage.raw_evidence) {
      expect(trail.querySelector(`[id$="${raw}"]`)).toHaveTextContent("Raw evidence: the bottom of the trail.");
    }
  });

  it("says plainly when the trail has a gap", () => {
    const gap = `obs_${"3".repeat(32)}`;
    const copy = structuredClone(payload) as any;
    copy.memories[0].lineage.nodes[0].parents.push(gap);
    copy.memories[0].lineage.missing.push(gap);
    renderView(memorySourceFrom(copy));
    const note = screen.getByText("Not found in the record").closest("[role=note]") as HTMLElement;
    expect(note).toHaveTextContent("the trail is incomplete");
    expect(note).toHaveTextContent(gap);
  });

  it("lists unreadable memory files instead of hiding them", () => {
    const copy = structuredClone(payload) as any;
    copy.unreadable.push({ path: "learnings/broken.md", revision: "a".repeat(40) });
    renderView(memorySourceFrom(copy));
    expect(screen.getByText("Files Serene could not read").closest("[role=note]")).toHaveTextContent(
      "learnings/broken.md",
    );
  });

  it("offers no way to edit, commit or approve memory", () => {
    const { container } = renderView();
    expect(container.querySelector("input, textarea, select, [contenteditable], form")).toBeNull();
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("invents no scores and shows no child or actor ids", () => {
    const { container } = renderView();
    expect(container).not.toHaveTextContent(/%|confidence|score/i);
    expect(container.innerHTML).not.toMatch(/chd_|act_/);
  });
});

describe("MemoryView states", () => {
  it("is honest when nothing is connected", () => {
    renderView({ status: "unconnected" });
    expect(screen.getByRole("heading", { name: "No memories yet" })).toBeInTheDocument();
  });

  it("announces loading", () => {
    renderView({ status: "loading" });
    expect(screen.getByRole("status")).toHaveTextContent("Loading memory");
  });

  it("fails closed on a payload that does not pass its checks", () => {
    const copy = structuredClone(payload) as any;
    copy.patches.find((p: any) => p.status === "REJECTED").rejection_reasons = [];
    const { container } = render(<MemoryView source={memorySourceFrom(copy)} retry={<button type="button">Try again</button>} />);
    expect(screen.getByRole("heading", { name: "Memory couldn’t be shown" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(container.querySelector("[data-patch-id], [data-memory-path]")).toBeNull();
  });

  it("says so when a connected record has nothing yet", () => {
    renderView({
      status: "ready",
      view: { ...view, memories: [], dream_runs: [], patches: [], unreadable: [] },
    });
    expect(screen.getByRole("heading", { name: "Nothing remembered yet" })).toBeInTheDocument();
  });
});
