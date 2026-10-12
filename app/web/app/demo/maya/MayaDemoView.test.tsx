import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MayaDemoView } from "./MayaDemoView";

afterEach(() => vi.unstubAllGlobals());

it("labels the fictional example and explains when it is unavailable", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false });
  vi.stubGlobal("fetch", fetch);
  render(<MayaDemoView />);
  expect(screen.getByText("A made-up example")).toBeVisible();
  expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
  expect(document.querySelector("[data-experiment-id]")).not.toBeInTheDocument();
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  expect(fetch).toHaveBeenLastCalledWith("/demo/maya/state", { cache: "no-store" });
});

it("rejects an invalid adapter response instead of rendering partial domain results", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
  render(<MayaDemoView />);
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(screen.queryByText("A shared summary")).not.toBeInTheDocument();
});
