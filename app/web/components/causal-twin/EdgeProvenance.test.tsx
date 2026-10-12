import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-causal-twin.json";
import { parseCausalTwin, type CausalEdge, type CausalTwin } from "@/lib/causal-twin/model";
import { CausalTwinSurface } from "./CausalTwinSurface";

const id = (prefix: string, n: number) => `${prefix}_${n.toString(16).padStart(32, "0")}`;
const HYP = (n: number) => id("hyp", n);
const fixture = (): CausalTwin => parseCausalTwin(structuredClone(payload));

const panel = () => screen.getByRole("complementary", { name: "Selected link" });
const section = (name: string) => within(panel()).getByRole("region", { name });
const entities = (el: HTMLElement) =>
  [...el.querySelectorAll("[data-entity-id]")].map((n) => n.getAttribute("data-entity-id"));
const roles = (el: HTMLElement) =>
  [...el.querySelectorAll("[data-entity-id]")].map((n) => [n.getAttribute("data-entity-id"), n.textContent]);

function renderTwin(twin: CausalTwin = fixture()) {
  const view = render(<CausalTwinSurface source={{ status: "ready", twin }} />);
  const listItem = (edgeId: string) =>
    view.container.querySelector<HTMLButtonElement>(`section button[data-edge-id="${edgeId}"]:not(.react-flow *)`)!;
  const mapLabel = (edgeId: string) =>
    view.container.querySelector<HTMLButtonElement>(`.react-flow button[data-edge-id="${edgeId}"]`)!;
  return { ...view, listItem, mapLabel };
}

// Every id an edge carries in its kernel fields, plus the links whose own
// provenance says they replaced it.
function idsOf(edge: CausalEdge, twin: CausalTwin): Set<string> {
  return new Set([
    ...twin.edges.filter((e) => e.provenance.supersedes === edge.edge_id).map((e) => e.edge_id),
    edge.edge_id,
    ...edge.support.map((s) => s.entity_id),
    ...edge.counterevidence,
    ...edge.contradicting_outcomes,
    ...edge.competing_edges,
    ...edge.experiments,
    ...edge.provenance.derived_from,
    ...edge.provenance.source_ids,
    ...(edge.provenance.supersedes ? [edge.provenance.supersedes] : []),
    ...edge.raw_evidence,
  ]);
}

describe("the edge provenance panel", () => {
  it("shows the selected link's own provenance", async () => {
    const user = userEvent.setup();
    const { mapLabel } = renderTwin();
    await user.click(mapLabel(HYP(1)));

    expect(panel().querySelector("[data-provenance-for]")).toHaveAttribute("data-provenance-for", HYP(1));
    expect(section("Why it is drawn this way")).toHaveTextContent("An experiment you approved supported it");
    expect(section("Why it is drawn this way")).toHaveTextContent("Level 5 of 5: Contextual learning");
    expect(entities(section("Evidence for it"))).toEqual([id("obs", 1), id("obs", 2), id("out", 1)]);
    expect(section("Evidence against it")).toHaveTextContent("Nothing recorded counts against it.");
    expect(entities(section("Experiments"))).toEqual([id("exp", 1)]);
    const scope = section("Where and when it holds");
    expect(scope).toHaveTextContent("School nights");
    expect(scope).toHaveTextContent("Valid from1 February 2026");
    expect(scope).toHaveTextContent("Review after1 April 2026");
    expect(scope).toHaveTextContent("In use");
    const why = section("What else could explain it");
    expect(why).toHaveTextContent("Dinner runs later on some school nights.");
    expect(why).toHaveTextContent("Homework left until after dinner, not the screens.");
    const lineage = section("How Serene came to hold it");
    expect(lineage).toHaveTextContent("Serene’s assistant (a language model)");
    expect(lineage).toHaveTextContent("Inferred by a language model");
    expect(lineage).toHaveTextContent("Recorded5 January 2026");
    const trail = within(lineage).getByRole("list", { name: /Evidence trail/ });
    expect(entities(trail)).toEqual([HYP(1), id("pat", 1), id("evd", 1), id("evd", 2)]);
  });

  it("shows different evidence for a different link", async () => {
    const user = userEvent.setup();
    const { mapLabel } = renderTwin();
    await user.click(mapLabel(HYP(1)));
    await user.click(mapLabel(HYP(2)));

    expect(panel().querySelector("[data-provenance-for]")).toHaveAttribute("data-provenance-for", HYP(2));
    expect(entities(section("Evidence for it"))).toEqual([id("obs", 3), id("obs", 4)]);
    expect(section("Experiments")).toHaveTextContent("No experiment has been set up for this link.");
    const trail = within(section("How Serene came to hold it")).getByRole("list", { name: /Evidence trail/ });
    expect(entities(trail)).toEqual([HYP(2), id("pat", 2), id("evd", 3), id("evd", 4)]);
    expect(panel()).not.toHaveTextContent(id("evd", 1));
    expect(panel()).not.toHaveTextContent(id("obs", 1));
  });

  it("keeps support and counterevidence distinguishable in words", async () => {
    const t = fixture();
    const edge = t.edges.find((e) => e.edge_id === HYP(6))!;
    Object.assign(edge, {
      counterevidence: [id("evd", 9), id("obs", 7), id("out", 3)],
    });
    const user = userEvent.setup();
    const { mapLabel } = renderTwin(t);
    await user.click(mapLabel(HYP(6)));

    expect(roles(section("Evidence for it"))).toEqual([[id("obs", 6), `Observation${id("obs", 6)}`]]);
    expect(roles(section("Evidence against it"))).toEqual([
      [id("evd", 9), `Evidence against it${id("evd", 9)}`],
      [id("obs", 7), `Observation against it${id("obs", 7)}`],
      [id("out", 3), `Experiment outcome: inconclusive${id("out", 3)}`],
    ]);
    // The same kind of item is never filed on both sides.
    const support = new Set(entities(section("Evidence for it")));
    expect(entities(section("Evidence against it")).some((x) => support.has(x))).toBe(false);
  });

  it("keeps a refuted link's provenance inspectable", async () => {
    const user = userEvent.setup();
    const { mapLabel } = renderTwin();
    await user.click(mapLabel(HYP(4)));

    expect(section("Why it is drawn this way")).toHaveTextContent("An experiment outcome contradicted it");
    expect(roles(section("Evidence against it"))).toEqual([
      [id("out", 2), `Experiment outcome: contradicts it${id("out", 2)}`],
    ]);
    // What once supported it is still shown, not hidden by the refutation.
    expect(entities(section("Evidence for it"))).toEqual([id("obs", 5)]);
    expect(entities(section("Experiments"))).toEqual([id("exp", 2)]);
    const rival = within(section("What else could explain it")).getByRole("button");
    expect(rival).toHaveAttribute("data-edge-ref", HYP(1));
    expect(rival).toHaveTextContent("Tested in context");
  });

  it("keeps superseded lineage visible in both directions", async () => {
    const user = userEvent.setup();
    const { mapLabel } = renderTwin();
    await user.click(mapLabel(HYP(5)));

    expect(section("Why it is drawn this way")).toHaveTextContent("set aside for a better-formed version");
    expect(entities(section("Evidence for it"))).toEqual([id("obs", 1)]);
    const replacedBy = within(section("Replaced and replacing")).getByRole("button");
    expect(replacedBy).toHaveAttribute("data-edge-ref", HYP(1));

    await user.click(replacedBy);
    expect(panel()).toHaveAttribute("data-selected-edge-id", HYP(1));
    const replaced = within(section("Replaced and replacing")).getByRole("button");
    expect(replaced).toHaveAttribute("data-edge-ref", HYP(5));
    expect(replaced).toHaveTextContent("Replaced");
    // Moving between links from the panel keeps keyboard focus in it.
    expect(within(panel()).getByRole("heading", { name: "Why it is drawn this way" })).toHaveFocus();
  });

  it("says so when the replacement is not on the map", async () => {
    const t = fixture();
    t.edges.find((e) => e.edge_id === HYP(1))!.provenance.supersedes = null;
    const user = userEvent.setup();
    const { mapLabel } = renderTwin(t);
    await user.click(mapLabel(HYP(5)));
    expect(section("Replaced and replacing")).toHaveTextContent("The link that replaced it is not on this map.");
  });

  it("shows missing optional provenance as honestly empty", async () => {
    const t = fixture();
    const edge = t.edges.find((e) => e.edge_id === HYP(7))!;
    Object.assign(edge.provenance, {
      created_by: { kind: "PARENT", actor_id: id("act", 2) },
      method: "PARENT_REPORT",
      model: null,
    });
    const user = userEvent.setup();
    const { listItem } = renderTwin(t);
    await user.click(listItem(HYP(7)));

    expect(section("Evidence for it")).toHaveTextContent("Nothing recorded supports it yet.");
    expect(section("Evidence against it")).toHaveTextContent("Nothing recorded counts against it.");
    expect(section("Experiments")).toHaveTextContent("No experiment has been set up for this link.");
    expect(section("Where and when it holds")).toHaveTextContent(
      "None. Only a contextual learning carries review dates.",
    );
    expect(section("What else could explain it")).toHaveTextContent(
      "Possible confoundersNone recorded.Other explanationsNone recorded.Competing linksNone recorded.",
    );
    expect(section("Replaced and replacing")).toHaveTextContent("No earlier link.");
    expect(section("Replaced and replacing")).toHaveTextContent("Not replaced.");
    const lineage = section("How Serene came to hold it");
    expect(lineage).toHaveTextContent("A parent");
    expect(lineage).not.toHaveTextContent("Model");
    // What the twin cannot carry is stated, not filled in.
    expect(section("Not shown here")).toHaveTextContent("Whether a piece of evidence came from outside your family");
  });

  it("follows ids, not matching text, between links", async () => {
    const t = fixture();
    const original = t.edges.find((e) => e.edge_id === HYP(5))!;
    // A different link that reads exactly like the replaced one.
    t.edges = [...t.edges, { ...original, edge_id: HYP(8), status: "CANDIDATE" }];
    const user = userEvent.setup();
    const { mapLabel } = renderTwin(t);
    await user.click(mapLabel(HYP(1)));

    const replaced = within(section("Replaced and replacing")).getByRole("button");
    expect(replaced).toHaveAttribute("data-edge-ref", HYP(5));
    await user.click(replaced);
    expect(panel()).toHaveAttribute("data-selected-edge-id", HYP(5));
    expect(mapLabel(HYP(5))).toHaveAttribute("aria-pressed", "true");
    expect(mapLabel(HYP(8))).toHaveAttribute("aria-pressed", "false");

    await user.click(mapLabel(HYP(8)));
    expect(section("Replaced and replacing")).toHaveTextContent("Not replaced.");
  });

  it("shows only recorded ids and dates, and no scores or citations", async () => {
    const user = userEvent.setup();
    const twin = fixture();
    const { listItem } = renderTwin(twin);
    for (const edge of twin.edges) {
      await user.click(listItem(edge.edge_id));
      const el = panel();
      expect(el).toHaveAttribute("data-selected-edge-id", edge.edge_id);
      const known = idsOf(edge, twin);
      for (const shown of entities(el)) expect(known, `${edge.edge_id} shows ${shown}`).toContain(shown);
      for (const ref of el.querySelectorAll("[data-edge-ref]")) {
        expect(known).toContain(ref.getAttribute("data-edge-ref"));
      }
      const dates = [...el.querySelectorAll("time")].map((t) => t.getAttribute("datetime"));
      expect(dates).toEqual(
        [edge.validity?.valid_from, edge.validity?.review_after, edge.provenance.created_at].filter(Boolean),
      );
      expect(el).not.toHaveTextContent(/%|confidence|probab|likel|score|strength|certain|https?:|doi/i);
      // Actor and child ids are not shown, nor even kept in the view model.
      const raw = payload.edges.find((e) => e.edge_id === edge.edge_id)!;
      expect(el).not.toHaveTextContent(raw.provenance.created_by.actor_id);
      expect(el).not.toHaveTextContent(raw.child_id);
      expect(JSON.stringify(edge)).not.toMatch(/\b(chd|act)_[0-9a-f]{32}\b/);
    }
  });

  it("opens from the keyboard and closes with Escape, handing focus back", async () => {
    const user = userEvent.setup();
    const { listItem } = renderTwin();
    listItem(HYP(4)).focus();
    await user.keyboard("{Enter}");
    expect(panel()).toHaveAttribute("data-selected-edge-id", HYP(4));

    within(panel()).getByRole("button", { name: "Clear" }).focus();
    await user.tab();
    expect(panel()).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    expect(screen.getByRole("complementary", { name: "Selected link" })).not.toHaveAttribute(
      "data-selected-edge-id",
    );
    expect(listItem(HYP(4))).toHaveFocus();

    await user.keyboard("{Enter}");
    await user.click(within(panel()).getByRole("button", { name: "Clear" }));
    expect(listItem(HYP(4))).toHaveFocus();
  });

  it("shortens long lists but says how many there are", async () => {
    const t = fixture();
    const edge = t.edges.find((e) => e.edge_id === HYP(2))!;
    edge.support = Array.from({ length: 40 }, (_, i) => ({ entity_id: id("obs", 100 + i), kind: "OBSERVATIONAL" }));
    const user = userEvent.setup();
    const { mapLabel } = renderTwin(t);
    await user.click(mapLabel(HYP(2)));

    const support = section("Evidence for it");
    expect(entities(support)).toHaveLength(6);
    const more = within(support).getByRole("button", { name: "Show all 40" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await user.click(more);
    expect(entities(support)).toHaveLength(40);
    expect(within(support).getByRole("button", { name: "Show fewer" })).toHaveAttribute("aria-expanded", "true");
  });
});
