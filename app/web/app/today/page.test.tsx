import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import recorded from "@/fixtures/synthetic-investigation.json";
import Page from "./page";

// The surface as it ships today: no feed is connected, so nothing from the
// synthetic investigation can appear.
describe("the shipped surface", () => {
  it("renders no fabricated production data", () => {
    const { container } = render(<Page />);
    const body = container.querySelector("#surface-body")!;
    expect(body).not.toHaveTextContent(/\d/);
    const row = recorded.snapshot.find((r) => r.projection === "investigations")!;
    for (const inv of Object.values(row.state) as any[]) {
      expect(container).not.toHaveTextContent(inv.question);
      for (const h of inv.hypotheses) expect(container).not.toHaveTextContent(h.statement);
    }
    expect(body.querySelector("[data-investigations], [data-next-action]")).toBeNull();
    expect(container).toHaveTextContent("Nothing to review today");
  });
});
