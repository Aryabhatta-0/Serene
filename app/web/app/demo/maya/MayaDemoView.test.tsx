import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { MayaDemoView } from "./MayaDemoView";

afterEach(() => vi.unstubAllGlobals());

it("labels the isolated demo and fails honestly when no canonical report is available", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false });
  vi.stubGlobal("fetch", fetch);
  render(<MayaDemoView />);
  expect(screen.getByText("DEMO MODE — synthetic Maya scenario")).toBeVisible();
  expect(await screen.findByRole("alert")).toHaveTextContent("unavailable or invalid");
  expect(document.querySelector("[data-experiment-id]")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Reload generated report" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  expect(fetch).toHaveBeenLastCalledWith("/demo/maya/state", { cache: "no-store" });
});

it("rejects an invalid adapter response instead of rendering partial domain results", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
  render(<MayaDemoView />);
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(screen.queryByText("Canonical artifact receipt")).not.toBeInTheDocument();
});
