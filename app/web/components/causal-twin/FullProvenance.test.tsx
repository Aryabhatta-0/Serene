import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-twin-provenance.json";
import { NOT_IN_TWIN } from "@/lib/causal-twin/provenance";
import { twinSourceFrom, type TwinSource } from "@/lib/causal-twin/source";
import { CausalTwinSurface } from "./CausalTwinSurface";

// The provenance panel with the kernel's provenance projection (#39, #75).
type Edge = (typeof payload.provenance.edges)[number];
const EDGES = payload.provenance.edges as Edge[];
const edgeWith = (status: string) => EDGES.find((e) => e.status === status)!;
const NODES = new Map(payload.provenance.nodes.map((n) => [n.entity_id, n]));

const panel = () => screen.getByRole("complementary", { name: "Selected link" });
const section = (name: string) => within(panel()).getByRole("region", { name });

const fullSource = () => twinSourceFrom(structuredClone(payload.twin), structuredClone(payload.provenance));

function renderWith(source: TwinSource = fullSource()) {
  const view = render(<CausalTwinSurface source={source} />);
  const select = async (edgeId: string) => {
    const button = view.container.querySelector<HTMLButtonElement>(
      `section button[data-edge-id="${edgeId}"]:not(.react-flow *)`,
    )!;
    await userEvent.click(button);
  };
  return { ...view, select };
}

describe("FullProvenance", () => {
  it.each(EDGES.map((e) => [e.status, e] as const))("renders every dimension for the %s edge", async (_status, edge) => {
    const { select } = renderWith();
    await select(edge.edge_id);
    const root = panel().querySelector(`[data-provenance-for="${edge.edge_id}"]`)!;
    expect(root).toHaveAttribute("data-provenance", "full");

    // Epistemic level, state and verification.
    expect(root.querySelector("[data-field=level]")).toHaveTextContent(`Level ${edge.epistemic_level} of 5`);
    expect(root.querySelector("[data-field=state]")).toBeVisible();
    expect(root.querySelector("[data-field=verification]")).toBeVisible();
    expect(root.querySelector("[data-field=complete]")).toHaveTextContent("Complete");

    // Support and counterexamples, with what each says and where it came from.
    for (const s of edge.support) {
      const item = section("Evidence for it").querySelector(`[data-entity-id="${s.entity_id}"]`)!;
      expect(item).toHaveTextContent(NODES.get(s.entity_id)!.summary);
      expect(item).toHaveAttribute("data-origin", NODES.get(s.entity_id)!.evidence_origin);
    }
    for (const c of edge.counterevidence) {
      expect(section("Evidence against it").querySelector(`[data-entity-id="${c.entity_id}"]`)).toBeVisible();
    }

    // Experiments and their outcomes, each outcome naming its experiment.
    for (const x of edge.experiments) {
      const card = section("Experiments").querySelector(`[data-experiment-id="${x.experiment_id}"]`)!;
      expect(card).toHaveTextContent(x.intervention);
      for (const o of x.outcomes) {
        const outcome = card.querySelector(`[data-outcome-id="${o.outcome_id}"]`)!;
        expect(outcome).toHaveAttribute("data-from-experiment", x.experiment_id);
        expect(outcome).toHaveTextContent(o.summary);
      }
    }

    // Scope.
    expect(root.querySelector("[data-field=scope]")).toBeVisible();

    // The ordered lineage, down to raw evidence.
    const steps = [...root.querySelectorAll('[data-chain="lineage"] > li')];
    expect(steps.map((li) => li.querySelector("[data-node-id]")!.getAttribute("data-node-id"))).toEqual(
      edge.lineage.steps.map((s) => s.entity_id),
    );
    for (const evd of edge.lineage.raw_evidence) {
      expect(root.querySelector(`[data-chain="lineage"] [data-node-id="${evd}"]`)).toHaveAttribute(
        "data-node-kind",
        "EVIDENCE",
      );
    }
    expect(root.querySelectorAll("[data-missing-node]")).toHaveLength(0);

    // Every provenance link lands on an entry in the panel.
    const links = [...root.querySelectorAll<HTMLAnchorElement>("a[data-provenance-link]")];
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      const target = link.getAttribute("href")!.slice(1);
      expect(document.getElementById(target), target).not.toBeNull();
    }

    // The twin-only limits are gone; only what stays private is listed.
    const limits = section("Not shown here");
    for (const line of NOT_IN_TWIN) expect(limits).not.toHaveTextContent(line);
    expect(limits).toHaveTextContent("Raw evidence stays private");
  });

  it("shows external evidence as external, with its public host", async () => {
    const { select } = renderWith();
    await select(edgeWith("SUPPORTED").edge_id);
    const external = panel().querySelector('[data-evidence-detail="external"]')!;
    expect(external).toHaveTextContent("Web page capture");
    expect(external).toHaveTextContent("example.org");
    expect(panel().querySelector('[data-evidence-detail="family"]')).toHaveTextContent("Parent report");
  });

  it("shows scope, validity and review for the level-5 edge", async () => {
    const { select } = renderWith();
    const edge = edgeWith("SUPPORTED");
    await select(edge.edge_id);
    const scope = section("Where and when it holds");
    expect(scope.querySelector("[data-field=valid-from] time")).toHaveAttribute("datetime", edge.validity!.valid_from);
    expect(scope.querySelector("[data-field=review-after] time")).toHaveAttribute(
      "datetime",
      edge.validity!.review_after,
    );
    expect(scope.querySelector("[data-field=review-status]")).toHaveTextContent("Next due");
    expect(scope.querySelector("[data-field=learning-status]")).toHaveTextContent("In use");
    expect(scope).toHaveTextContent(edge.learning!.statement);
    for (const trigger of edge.learning!.retest_triggers) expect(scope).toHaveTextContent(trigger);
  });

  it("shows why a link was replaced and why one was refuted", async () => {
    const { select } = renderWith();
    const superseded = edgeWith("SUPERSEDED");
    await select(superseded.edge_id);
    const replaced = section("Replaced and refuted");
    expect(replaced.querySelector("[data-field=supersession-reason]")).toHaveTextContent(superseded.supersession.reason!);
    expect(replaced.querySelector(`button[data-edge-ref="${superseded.supersession.superseded_by}"]`)).toBeVisible();

    const refuted = edgeWith("REFUTED");
    await select(refuted.edge_id);
    const refutation = section("Replaced and refuted").querySelector("[data-field=refutation]")!;
    expect(refutation).toHaveTextContent("CONTRADICTING_OUTCOME");
    expect(refutation.querySelector(`[data-provenance-link="${refuted.refutation!.outcome_ids[0]}"]`)).toBeVisible();
  });

  it("shows a missing provenance node instead of inventing it", async () => {
    const provenance = structuredClone(payload.provenance) as unknown as Record<string, any>;
    const edge = provenance.edges.find((e: any) => e.status === "REFUTED");
    const obs = edge.support.find((s: any) => s.entity_id.startsWith("obs_")).entity_id;
    const referrers: string[] = provenance.nodes
      .filter((n: any) => n.parents.includes(obs))
      .map((n: any) => n.entity_id);
    provenance.nodes = provenance.nodes
      .filter((n: any) => n.entity_id !== obs)
      .map((n: any) => (n.parents.includes(obs) ? { ...n, missing: [obs] } : n));
    provenance.missing = [{ entity_id: obs, referenced_by: [...referrers, edge.edge_id].sort() }];
    for (const e of provenance.edges) {
      if (e.lineage.steps.some((s: any) => s.entity_id === obs)) {
        e.lineage.steps = e.lineage.steps.filter((s: any) => s.entity_id !== obs);
        e.lineage.missing = [{ entity_id: obs, referenced_by: referrers }];
        e.lineage.complete = false;
      }
    }
    const source = twinSourceFrom(structuredClone(payload.twin), provenance);
    expect(source.status).toBe("ready");
    const { select } = renderWith(source);
    await select(edge.edge_id);
    expect(panel().querySelector(`[data-entity-id="${obs}"][data-missing-node]`)).toHaveTextContent(
      "Missing provenance node",
    );
    expect(panel().querySelector(`[data-chain] [data-missing-node="${obs}"]`)).toHaveTextContent(
      "Missing provenance node",
    );
    expect(panel().querySelector("[data-field=complete]")).toHaveTextContent("Incomplete: 1 missing provenance node");
  });

  it("falls back to the twin-only panel, saying what it cannot show, without a projection", async () => {
    const { select } = renderWith(twinSourceFrom(structuredClone(payload.twin)));
    const edge = edgeWith("SUPPORTED");
    await select(edge.edge_id);
    const root = panel().querySelector(`[data-provenance-for="${edge.edge_id}"]`)!;
    expect(root).not.toHaveAttribute("data-provenance", "full");
    expect(section("Not shown here")).toHaveTextContent(NOT_IN_TWIN[0]);
  });
});
