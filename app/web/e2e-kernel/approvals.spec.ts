import { test, expect, type WebSocketRoute } from "@playwright/test";

// Synthetic Auth service + real HTTP/PG kernel. Realtime is deliberately
// held so we can prove a recorded HTTP decision never changes the UI stage.
// Every row delivered below was read from the production projection store.
const HOST = "http://127.0.0.1:8806";
type Row = { child_id: string; projection: string; state: any; last_sequence: number; last_event_hash: string };

test("signed-in browser decisions reach admission, and only projections change the stage", async ({ page, request }) => {
  const sockets: { ws: WebSocketRoute; topic: string; join: string }[] = [];
  await page.routeWebSocket(/\/realtime\/v1\/websocket/, (ws) => {
    ws.onMessage((raw) => {
      const [join, ref, topic, event, payload] = JSON.parse(String(raw));
      if (event === "phx_join") {
        sockets.push({ ws, topic, join });
        ws.send(JSON.stringify([join, ref, topic, "phx_reply", {
          status: "ok", response: { postgres_changes: payload.config.postgres_changes.map((p: any) => ({ ...p, id: 1 })) },
        }]));
      } else if (event === "heartbeat" || event === "phx_leave") {
        ws.send(JSON.stringify([join, ref, topic, "phx_reply", { status: "ok", response: {} }]));
      }
    });
  });

  await page.goto("/sign-in?next=/experiments");
  await page.getByLabel("Email").fill("parent@example.org");
  await page.getByLabel("Password").fill("fake-synthetic-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3278/experiments");
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  const pending = page.locator('article[data-safety="GREEN"][data-phase="AWAITING_APPROVAL"]').first();
  await expect(pending).toBeVisible();
  const id = (await pending.getAttribute("data-experiment-id"))!;
  const card = page.locator(`article[data-experiment-id="${id}"]`);

  const session = await request.post(`${HOST}/auth/v1/token`, { data: { email: "parent@example.org", password: "fake-synthetic-only" } });
  const { access_token: access } = await session.json();
  const headers = { Authorization: `Bearer ${access}` };
  const snapshot = async (): Promise<Row[]> => (await request.get(`${HOST}/rest/v1/projection_state`, { headers })).json();
  const rows = await snapshot();
  const child = rows[0].child_id;
  const view = rows.find((r) => r.projection === "experiments")!.state;
  const approval = view.experiments.find((e: any) => e.experiment_id === id).approval;
  const originalHead = await (await request.get(`${HOST}/__test/head`)).json();
  const relay = (command: any, token = access) => request.post("/api/approvals", {
    headers: { origin: "http://127.0.0.1:3278", authorization: `Bearer ${token}` }, data: { child_id: child, command },
  });
  const cmd = { approval_request_id: approval.approval_request_id, decision: "APPROVE", shown_intervention_digest: approval.intervention_digest,
    shown_safety_class: "GREEN", request_id: "browser-stale-0001" };

  // The kernel refuses stale data and non-parent sessions before any decision.
  const stale = await relay({ ...cmd, shown_intervention_digest: "0".repeat(64) });
  expect((await stale.json()).reason_codes).toContain("INTERVENTION_DIGEST_MISMATCH");
  const redAttempt = await relay({ ...cmd, request_id: "browser-red-0001", shown_safety_class: "RED" });
  expect((await redAttempt.json()).reason_codes).toContain("RED_CANNOT_BE_APPROVED");
  const amber = view.experiments.find((e: any) => e.safety_class === "AMBER").approval;
  const amberCmd = { ...cmd, approval_request_id: amber.approval_request_id,
    shown_intervention_digest: amber.intervention_digest, request_id: "browser-amber-0001" };
  expect((await (await relay(amberCmd)).json()).reason_codes).toContain("SAFETY_CLASS_NOT_ACKNOWLEDGED");
  expect((await (await relay({ ...amberCmd, request_id: "browser-amber-0002", shown_safety_class: "AMBER" })).json()).reason_codes).toContain("AMBER_DELIBERATION_TOO_SHORT");
  expect((await relay({ ...cmd, request_id: "browser-forged-0001" }, "fake-forged.jwt.token")).status()).toBe(401);
  for (const email of ["other@example.org", "caregiver@example.org"]) {
    const other = await (await request.post(`${HOST}/auth/v1/token`, { data: { email, password: "fake-synthetic-only" } })).json();
    expect((await relay({ ...cmd, request_id: `browser-forbidden-${email.split("@")[0]}` }, other.access_token)).status()).toBe(403);
    const otherRows = await (await request.get(`${HOST}/rest/v1/projection_state`, { headers: { authorization: `Bearer ${other.access_token}` } })).json();
    expect(otherRows.every((r: Row) => r.projection === "active_learnings")).toBe(true);
  }
  expect(await (await request.get(`${HOST}/rest/v1/projection_state`)).json()).toEqual([]);
  expect(await (await request.get(`${HOST}/__test/head`)).json()).toEqual(originalHead);

  // RED has no action, including after an authenticated sign-in.
  const red = page.locator('article[data-safety="RED"]');
  await expect(red).toHaveAttribute("data-phase", "BLOCKED");
  await expect(red.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);

  await card.getByRole("button", { name: "Approve", exact: true }).click();
  const sent = page.waitForRequest((r) => r.url().endsWith("/api/approvals") && r.method() === "POST");
  await card.getByRole("button", { name: "Yes, approve" }).click();
  const browserRequest = await sent;
  await expect(card.getByText(/Serene recorded your approval/)).toBeVisible();
  await expect(card).toHaveAttribute("data-phase", "AWAITING_APPROVAL");

  const after = await (await request.get(`${HOST}/__test/head`)).json();
  expect(after.decisions).toBe(originalHead.decisions + 1);
  const replay = await request.post("/api/approvals", { headers: { "content-type": "application/json", origin: "http://127.0.0.1:3278", authorization: `Bearer ${access}` }, data: browserRequest.postData()! });
  expect((await replay.json()).outcome).toBe("APPROVAL_GRANTED");
  expect(await (await request.get(`${HOST}/__test/head`)).json()).toEqual(after);

  function deliver(row: Row) {
    const { ws, topic, join } = sockets[sockets.length - 1];
    ws.send(JSON.stringify([join, null, topic, "postgres_changes", { ids: [1], data: {
      schema: "serene", table: "projection_state", type: "UPDATE", commit_timestamp: new Date().toISOString(),
      columns: [], record: row, old_record: {}, errors: [],
    } }]));
  }
  for (const row of await snapshot()) deliver(row);
  await expect(card).toHaveAttribute("data-phase", "APPROVED");

  // Another real pending request is declined through the same browser UI.
  const decline = page.locator('article[data-phase="AWAITING_APPROVAL"]').first();
  const declineId = (await decline.getAttribute("data-experiment-id"))!;
  await decline.getByRole("button", { name: /Decline/ }).click();
  await decline.getByRole("button", { name: /Yes, decline/ }).click();
  await expect(decline.getByText(/Serene recorded/)).toBeVisible();
  await expect(decline).toHaveAttribute("data-phase", "AWAITING_APPROVAL");
  for (const row of await snapshot()) deliver(row);
  await expect(page.locator(`article[data-experiment-id="${declineId}"]`)).toHaveAttribute("data-phase", "ABANDONED");
  expect(await (await request.get(`${HOST}/__test/check`)).json()).toEqual({ verified: true });
});
