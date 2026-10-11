import { describe, expect, it } from "vitest";
import { pageExtensions } from "./fixture-routes.mjs";

describe("fixture routes", () => {
  it("are left out of a normal build", () => {
    expect(pageExtensions({})).not.toContain("fixture.tsx");
    expect(pageExtensions({ SERENE_FIXTURE_ROUTES: "0" })).not.toContain("fixture.tsx");
  });

  it("exist only when the test build asks for them", () => {
    expect(pageExtensions({ SERENE_FIXTURE_ROUTES: "1" })).toContain("fixture.tsx");
  });
});
