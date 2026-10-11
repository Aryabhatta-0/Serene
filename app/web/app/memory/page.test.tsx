import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import payload from "@/fixtures/synthetic-memory-dream.json";
import MemoryPage from "./page";

// The surface as it ships today: no family record is connected, so it must
// show nothing from the synthetic fixture.
describe("the Memory surface", () => {
  it("renders no fabricated production data", () => {
    const { container } = render(<MemoryPage />);
    const body = container.querySelector("#surface-body")!;
    expect(body).not.toHaveTextContent(/\d/);
    for (const memory of payload.memories) {
      expect(container).not.toHaveTextContent(memory.title);
      expect(container).not.toHaveTextContent(memory.body);
    }
    expect(container).not.toHaveTextContent(/(mpt|lrn|evd|obs|pat|hyp)_/);
    expect(body.querySelector("[data-memory-review], [data-patch-id], [data-memory-path]")).toBeNull();
    expect(container).toHaveTextContent("No memories yet");
  });
});
