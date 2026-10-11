import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import payload from "@/fixtures/synthetic-causal-twin.json";
import { CATEGORY_ORDER } from "@/lib/causal-twin/categories";
import { parseCausalTwin } from "@/lib/causal-twin/model";
import { UNCONNECTED, twinSourceFrom, type TwinSource } from "@/lib/causal-twin/source";
import { CausalTwinView } from "./CausalTwinView";

const HYP = (n: number) => `hyp_${n.toString(16).padStart(32, "0")}`;
const ready = (): TwinSource => ({ status: "ready", twin: parseCausalTwin(payload) });
const edgeGroup = (container: HTMLElement, id: string) =>
  container.querySelector<SVGGElement>(`g[data-edge-id="${id}"]`);
const mapLabel = (container: HTMLElement, id: string) =>
  container.querySelector<HTMLButtonElement>(`.react-flow button[data-edge-id="${id}"]`)!;

// Every string the synthetic fixture could put on screen.
const FIXTURE_TEXT = [
  ...payload.edges.map((e) => e.relationship),
  "Screens after dinner",
  "Bedtime resistance",
  "After school snack",
];

describe("CausalTwinView with a twin", () => {
  it("draws each epistemic category with its own line, not only its own colour", () => {
    const { container } = render(<CausalTwinView source={ready()} />);
    const signatures = new Set<string>();
    for (const category of CATEGORY_ORDER) {
      const group = container.querySelector(`.react-flow g[data-category="${category}"]`);
      expect(group, category).not.toBeNull();
      const stroke = group!.querySelector("path[data-stroke]")!;
      signatures.add(
        [
          stroke.getAttribute("stroke-dasharray") ?? "solid",
          stroke.getAttribute("stroke-width"),
          group!.querySelector("[data-strike]") ? "struck" : "",
          group!.querySelector("[data-hollow]") ? "hollow" : "",
        ].join("|"),
      );
      // The category is also written on the link itself.
      const label = container.querySelector(`.react-flow button[data-category="${category}"]`);
      expect(label).not.toBeNull();
    }
    expect(signatures.size).toBe(CATEGORY_ORDER.length);
    expect(mapLabel(container, HYP(1))).toHaveTextContent("Tested in context");
    expect(mapLabel(container, HYP(2))).toHaveTextContent("Observed");
    expect(mapLabel(container, HYP(3))).toHaveTextContent("Hypothesis");
    expect(mapLabel(container, HYP(4))).toHaveTextContent("Refuted");
    expect(mapLabel(container, HYP(5))).toHaveTextContent("Replaced");
  });

  it("renders the graph from the twin it is given", () => {
    const twin = parseCausalTwin(payload);
    const { container, rerender } = render(<CausalTwinView source={{ status: "ready", twin }} />);
    const drawn = () =>
      [...container.querySelectorAll(".react-flow g[data-edge-id]")].map((g) => g.getAttribute("data-edge-id"));
    expect(drawn()).toEqual(twin.edges.filter((e) => e.cause).map((e) => e.edge_id));
    expect(container.querySelectorAll(".react-flow [data-variable]")).toHaveLength(6);

    // A different twin is a different map: nothing on it is fixed in the markup.
    const smaller = { ...twin, edges: twin.edges.filter((e) => e.edge_id === HYP(2)) };
    rerender(<CausalTwinView source={{ status: "ready", twin: smaller }} />);
    expect(drawn()).toEqual([HYP(2)]);
    expect([...container.querySelectorAll(".react-flow [data-variable]")].map((n) => n.textContent)).toEqual(
      ["Late bedtime", "Morning irritability"],
    );
  });

  it("keeps refuted links on the map, visible and struck through", () => {
    const { container } = render(<CausalTwinView source={ready()} />);
    const refuted = edgeGroup(container, HYP(4))!;
    expect(refuted).not.toBeNull();
    expect(refuted.querySelector("[data-strike]")).not.toBeNull();
    const label = mapLabel(container, HYP(4));
    expect(label).toBeVisible();
    expect(label).toHaveTextContent("A sugary snack after school makes bedtime harder.");
    // And in the list, under its own heading.
    const list = screen.getByRole("region", { name: "Every link, by how firmly it is held" });
    expect(within(list).getByRole("heading", { name: "Refuted" })).toBeVisible();
    const legend = screen.getByRole("list", { name: "How links are drawn" });
    expect(legend.querySelector('[data-category="refuted"]')).toHaveTextContent("Refuted1 link");
  });

  it("lists a link with unnamed variables but does not draw it", () => {
    const { container } = render(<CausalTwinView source={ready()} />);
    expect(edgeGroup(container, HYP(7))).toBeNull();
    const list = screen.getByRole("region", { name: "Every link, by how firmly it is held" });
    expect(within(list).getByText("Something about weekends changes how the week starts.")).toBeVisible();
  });

  it("exposes the selected link's identity for the provenance panel", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { container } = render(
      <CausalTwinView
        source={ready()}
        onSelectedEdgeChange={onChange}
        renderEdgeDetail={(edge) => <p data-testid="detail">{edge.edge_id}</p>}
      />,
    );
    expect(screen.getByRole("complementary", { name: "Selected link" })).not.toHaveAttribute(
      "data-selected-edge-id",
    );

    await user.click(mapLabel(container, HYP(4)));
    expect(onChange).toHaveBeenLastCalledWith(HYP(4));
    const panel = screen.getByRole("complementary", { name: "Selected link" });
    expect(panel).toHaveAttribute("data-selected-edge-id", HYP(4));
    expect(panel).toHaveTextContent(HYP(4));
    expect(panel).toHaveTextContent("Refuted");
    expect(panel).toHaveTextContent("including 1 experiment outcome that contradicts it");
    expect(screen.getByTestId("detail")).toHaveTextContent(HYP(4));
    expect(mapLabel(container, HYP(4))).toHaveAttribute("aria-pressed", "true");
    expect(edgeGroup(container, HYP(4))).toHaveAttribute("data-selected", "true");

    // The list selects too, and from the keyboard.
    const item = container.querySelector<HTMLButtonElement>(`section button[data-edge-id="${HYP(1)}"]:not(.react-flow *)`)!;
    item.focus();
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenLastCalledWith(HYP(1));
    expect(screen.getByRole("complementary", { name: "Selected link" })).toHaveAttribute(
      "data-selected-edge-id",
      HYP(1),
    );

    // Choosing the selected link again clears it (the buttons are toggles).
    await user.click(mapLabel(container, HYP(1)));
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(mapLabel(container, HYP(1))).toHaveAttribute("aria-pressed", "false");

    await user.click(mapLabel(container, HYP(2)));
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("follows a controlled selection", () => {
    render(<CausalTwinView source={ready()} selectedEdgeId={HYP(2)} />);
    expect(screen.getByRole("complementary", { name: "Selected link" })).toHaveAttribute(
      "data-selected-edge-id",
      HYP(2),
    );
  });

  it("offers pan/zoom and fit-to-view controls with names", () => {
    render(<CausalTwinView source={ready()} />);
    for (const name of ["Zoom in", "Zoom out", "Fit to view"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
  });

  it("shows no percentages or scores: counts are of recorded items only", () => {
    const { container } = render(<CausalTwinView source={ready()} />);
    expect(container).not.toHaveTextContent(/%|confidence|probability|likely/i);
  });
});

describe("CausalTwinView without a twin", () => {
  it("says no record is connected, and draws nothing", () => {
    const { container } = render(<CausalTwinView source={UNCONNECTED} />);
    expect(screen.getByRole("heading", { name: "No links to draw yet" })).toBeVisible();
    expect(container.querySelector(".react-flow")).toBeNull();
    expect(container).not.toHaveTextContent(/\d/);
    for (const text of FIXTURE_TEXT) expect(container).not.toHaveTextContent(text);
    // The legend still explains all the notation, refuted included.
    expect(screen.getByRole("region", { name: "How links will be drawn" })).toHaveTextContent("Refuted");
  });

  it("shows an empty twin as empty", () => {
    const twin = { ...parseCausalTwin(payload), edges: [] };
    const { container } = render(<CausalTwinView source={{ status: "ready", twin }} />);
    expect(screen.getByRole("heading", { name: "No links recorded yet" })).toBeVisible();
    expect(container.querySelector(".react-flow")).toBeNull();
  });

  it("shows loading and errors honestly", async () => {
    const { container, rerender } = render(<CausalTwinView source={{ status: "loading" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the Causal Twin");
    expect(container.querySelector(".react-flow")).toBeNull();

    const retry = vi.fn();
    rerender(<CausalTwinView source={twinSourceFrom({ twin_version: "causal-twin/1" })} onRetry={retry} />);
    expect(screen.getByRole("heading", { name: "The map couldn’t be drawn" })).toBeVisible();
    expect(container.querySelector(".react-flow")).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
