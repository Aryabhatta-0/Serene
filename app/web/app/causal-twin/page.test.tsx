import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-causal-twin.json";
import CausalTwinPage from "./page";

// The surface as it ships today: no family record is connected, so it must
// draw no map and nothing from the synthetic fixture.
describe("the Causal Twin surface", () => {
  it("renders no fabricated production data", () => {
    const { container } = render(<CausalTwinPage />);
    const body = container.querySelector("#surface-body")!;
    expect(body.querySelector(".react-flow, svg g[data-edge-id], [data-variable]")).toBeNull();
    expect(body).not.toHaveTextContent(/\d/);
    for (const edge of payload.edges) {
      expect(container).not.toHaveTextContent(edge.relationship);
      for (const note of [...edge.confounders, ...edge.alternative_explanations]) {
        expect(container).not.toHaveTextContent(note);
      }
    }
    expect(container).not.toHaveTextContent(/(hyp|evd|obs|out|exp|pat)_/);
    expect(body.querySelector("[data-provenance-for], [data-selected-edge-id]")).toBeNull();
    expect(container).toHaveTextContent("No links to draw yet");
    expect(container).toHaveTextContent("No family record connected");
  });
});
