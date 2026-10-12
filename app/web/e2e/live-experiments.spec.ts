import { expect, test, type Page } from "@playwright/test";
import payload from "../fixtures/synthetic-experiments.json";

// Deciding on /experiments through the real transport (Issue #84). The page's
// own code POSTs to /api/approvals; the test answers in place of the kernel and
// then delivers the projection row the kernel publishes. The stage changes only
// after that row arrives, never on the answer alone. Synthetic data only.
const green = payload.experiments.find((e) => e.phase === "AWAITING_APPROVAL" && e.safety_class === "GREEN")!;
const red = payload.experiments.find((e) => e.safety_class === "RED")!;
const card = (page: Page, id: string) => page.locator(`article[data-experiment-id="${id}"]`);

async function signIn(page: Page) {
  await page.goto("/fixtures/live-experiments");
  await page.getByLabel("Email").fill("parent@example.org");
  await page.getByLabel("Password").fill("fake-synthetic-only");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Family record connected")).toBeVisible();
}

test("approving shows the kernel's answer, and the stage moves only when the projection does", async ({ page }) => {
  const sent: { headers: Record<string, string>; body: any }[] = [];
  await page.route("**/api/approvals", async (route) => {
    sent.push({ headers: route.request().headers(), body: route.request().postDataJSON() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ outcome: "APPROVAL_GRANTED", event_ids: [`evt_${"9".repeat(32)}`], reason_codes: [] }),
    });
  });
  await signIn(page);
  const article = card(page, green.experiment_id);
  await expect(article).toHaveAttribute("data-phase", "AWAITING_APPROVAL");
  await article.getByRole("button", { name: "Approve" }).click();
  await article.getByRole("button", { name: "Yes, approve" }).click();
  await expect(article.locator('[data-result="recorded"]')).toBeVisible();

  expect(sent).toHaveLength(1);
  expect(sent[0].headers.authorization).toMatch(/^Bearer fake-access\./);
  expect(sent[0].body.child_id).toBe(`chd_${"a".repeat(32)}`);
  expect(sent[0].body.command).toMatchObject({
    approval_request_id: green.approval!.approval_request_id,
    decision: "APPROVE",
    shown_safety_class: "GREEN",
  });
  expect(JSON.stringify(sent[0].body)).not.toMatch(/actor|user_id/);
  await expect(article).toHaveAttribute("data-phase", "AWAITING_APPROVAL"); // not yet recorded here

  await page.getByRole("button", { name: "Kernel publishes" }).click();
  await expect(article).toHaveAttribute("data-phase", "APPROVED");
});

test("a refusal is shown with its reasons and nothing changes", async ({ page }) => {
  await page.route("**/api/approvals", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ outcome: "REFUSED", event_ids: [], reason_codes: ["APPROVAL_EXPIRED"] }),
    }),
  );
  await signIn(page);
  const article = card(page, green.experiment_id);
  await article.getByRole("button", { name: "Approve" }).click();
  await article.getByRole("button", { name: "Yes, approve" }).click();
  await expect(article.locator('[data-reason-code="APPROVAL_EXPIRED"]')).toBeVisible();
  await expect(article).toHaveAttribute("data-phase", "AWAITING_APPROVAL");
});

test("RED can never be approved, signed in or not", async ({ page }) => {
  await signIn(page);
  await expect(card(page, red.experiment_id).getByRole("button", { name: "Approve" })).toHaveCount(0);
  await expect(card(page, red.experiment_id).locator('[data-decision="not-approvable"]')).toBeVisible();
});
