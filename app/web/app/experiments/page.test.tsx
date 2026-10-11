import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-experiments.json";
import ExperimentsPage from "./page";

// The surface as it ships today: no family record and no decision transport
// are connected, so it shows nothing from the fixture and offers no decision.
describe("the Experiments surface", () => {
  it("renders no fabricated production data and no decision controls", () => {
    const { container } = render(<ExperimentsPage />);
    const body = container.querySelector("#surface-body")!;
    expect(body).not.toHaveTextContent(/\d/);
    for (const e of payload.experiments) expect(container).not.toHaveTextContent(e.intervention.description);
    expect(container).not.toHaveTextContent(/(exp|apr|hyp)_/);
    expect(body.querySelector("[data-experiments], [data-experiment-id], button")).toBeNull();
    expect(container).toHaveTextContent("No experiments proposed");
  });
});
