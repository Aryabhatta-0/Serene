import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import SurfaceError from "./error";
import GlobalError from "./global-error";

afterEach(() => vi.restoreAllMocks());

describe("error-boundary privacy", () => {
  for (const [name, Boundary, code] of [
    ["view", SurfaceError, "Serene view error"],
    ["root", GlobalError, "Serene client error"],
  ] as const) {
    it(`${name} removes private messages, stacks and digests while preserving retry`, async () => {
      const log = vi.spyOn(console, "error").mockImplementation(() => {});
      const privateText = "Synthetic Maya's private narrative and synthetic session secret";
      const error = Object.assign(new Error(privateText), { digest: privateText });
      error.stack = privateText;
      const reset = vi.fn();
      const { container } = render(<Boundary error={error} reset={reset} />);
      expect(log).toHaveBeenCalledWith(code);
      expect(JSON.stringify(log.mock.calls)).not.toContain(privateText);
      expect(container).not.toHaveTextContent(privateText);
      await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
      expect(reset).toHaveBeenCalledOnce();
    });
  }
});
