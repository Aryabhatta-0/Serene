import { test, expect, type WebSocketRoute } from "@playwright/test";

// Shipped /memory + real Git, ledger, publisher, PostgreSQL and RLS.
// Auth is synthetic; WS delivery is controlled to prove publish-only updates.
const HOST = "http://127.0.0.1:8806";
test("Memory/Dream updates only from the scoped published projection", async ({ page, request }) => {
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
  await page.goto("/sign-in?next=/memory");
  await page.getByLabel("Email").fill("parent@example.org");
  await page.getByLabel("Password").fill("fake-synthetic-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  await expect(page.getByText("Nothing remembered yet")).toBeVisible();

  expect((await request.post(`${HOST}/__test/memory`)).ok()).toBe(true);
  // A completed Dream and Git commit alone do not optimistically alter the browser.
  await expect(page.locator("[data-memory-path]")).toHaveCount(0);
  const session = await (await request.post(`${HOST}/auth/v1/token`, {
    data: { email: "parent@example.org", password: "fake-synthetic-only" },
  })).json();
  const headers = { authorization: `Bearer ${session.access_token}` };
  const rows = await (await request.get(`${HOST}/rest/v1/projection_state`, { headers })).json();
  const row = rows.find((r: any) => r.projection === "memory_dream");
  expect(row.state.memory_head).toMatch(/^[0-9a-f]{40}$/);
  expect(row.state.memories).toHaveLength(1);
  expect(JSON.stringify(row.state)).not.toMatch(/(?:chd_|act_|child_id|actor_id)/);
  const { ws, topic, join } = sockets[sockets.length - 1];
  ws.send(JSON.stringify([join, null, topic, "postgres_changes", { ids: [1], data: {
    schema: "serene", table: "projection_state", type: "UPDATE", commit_timestamp: new Date().toISOString(),
    columns: [], record: row, old_record: {}, errors: [],
  } }]));
  await expect(page.locator("[data-memory-path]")).toHaveCount(1);
  await expect(page.getByText(row.state.memory_head, { exact: true })).toBeVisible();
  await expect(page.locator('[data-status="REJECTED"]')).toContainText("Not enough evidence");
  await expect(page.locator('[data-status="COMMITTED"]')).toContainText("Kept");

  for (const email of ["other@example.org", "caregiver@example.org"]) {
    const other = await (await request.post(`${HOST}/auth/v1/token`, {
      data: { email, password: "fake-synthetic-only" },
    })).json();
    const hidden = await (await request.get(`${HOST}/rest/v1/projection_state`, {
      headers: { authorization: `Bearer ${other.access_token}` },
    })).json();
    expect(hidden.some((r: any) => r.projection.startsWith("memory_"))).toBe(false);
  }
  // A browser reload obtains the current snapshot without WS replay history.
  await page.reload();
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  await expect(page.locator("[data-memory-path]")).toHaveCount(1);
  expect(await (await request.get(`${HOST}/__test/check`)).json()).toEqual({ verified: true });
});
