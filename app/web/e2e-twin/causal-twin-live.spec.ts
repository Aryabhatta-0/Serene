import { test, expect, type Page, type WebSocketRoute } from "@playwright/test";

// The shipped /causal-twin on the signed-in family record, against a loopback
// test kernel (tests/web_twin_server.py): synthetic Auth, real PostgreSQL with
// the production ledger, projection publisher, migrations and RLS. Every row
// delivered below was read from serene.projection_state as the signed-in
// user; Realtime delivery is held by the test so each change is deliberate.
const HOST = "http://127.0.0.1:8806";
const PASSWORD = "fake-synthetic-only";
const PRIVATE = /\b(chd|act|src)_[0-9a-f]{32}\b/;
type Row = { child_id: string; projection: string; state: any; last_sequence: number; last_event_hash: string };
type Socket = { ws: WebSocketRoute; topic: string; join: string; open: boolean };

const listButton = (page: Page, id: string) => page.locator(`section button[data-edge-id="${id}"]:not(.react-flow *)`);
const provenance = (page: Page, id: string) => page.locator(`[data-provenance-for="${id}"]`);

test("a signed-in parent's live Causal Twin: projection only, RLS-scoped, live, resynced and child-scoped", async ({ page, request }) => {
  const sockets: Socket[] = [];
  await page.routeWebSocket(/\/realtime\/v1\/websocket/, (ws) => {
    ws.onMessage((raw) => {
      const [join, ref, topic, event, payload] = JSON.parse(String(raw));
      if (event === "phx_join") {
        sockets.push({ ws, topic, join, open: true });
        ws.send(JSON.stringify([join, ref, topic, "phx_reply", {
          status: "ok", response: { postgres_changes: payload.config.postgres_changes.map((p: any) => ({ ...p, id: 1 })) },
        }]));
      } else if (event === "heartbeat" || event === "phx_leave") {
        ws.send(JSON.stringify([join, ref, topic, "phx_reply", { status: "ok", response: {} }]));
      }
    });
  });
  // Everything the browser asks for, to prove it reads projections and the guardian list only.
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));

  const signInAs = async (email: string) =>
    (await (await request.post(`${HOST}/auth/v1/token`, { data: { email, password: PASSWORD } })).json()).access_token as string;
  const rowsAs = async (token: string | null): Promise<Row[]> =>
    (await request.get(`${HOST}/rest/v1/projection_state`, token ? { headers: { authorization: `Bearer ${token}` } } : {})).json();
  const parentToken = await signInAs("parent@example.org");
  const twinOf = async (child: string) => (await rowsAs(parentToken)).find((r) => r.child_id === child && r.projection === "causal_twin")!;
  const deliver = (row: Row) => {
    const live = sockets.filter((s) => s.open && s.topic.endsWith(row.child_id));
    expect(live.length).toBeGreaterThan(0);
    const { ws, topic, join } = live[live.length - 1];
    ws.send(JSON.stringify([join, null, topic, "postgres_changes", { ids: [1], data: {
      schema: "serene", table: "projection_state", type: "UPDATE", commit_timestamp: new Date().toISOString(),
      columns: [], record: row, old_record: {}, errors: [],
    } }]));
  };
  const { parent: children, other: [theirs] } = await (await request.get(`${HOST}/__test/children`)).json();
  // `first` has a refuted and a candidate link; `second` one candidate link.
  const refutedIn = async (child: string) => (await twinOf(child)).state.edges.some((e: any) => e.status === "REFUTED");
  const first: string = (await refutedIn(children[0])) ? children[0] : children[1];
  const second: string = children.find((c: string) => c !== first);

  // RLS, as the browser's own transport sees it.
  const own = await rowsAs(parentToken);
  expect(new Set(own.map((r) => r.child_id))).toEqual(new Set([first, second]));
  for (const row of own.filter((r) => r.projection === "causal_twin")) {
    expect(JSON.stringify(row.state)).not.toMatch(PRIVATE);
    expect(row.state.version).toBe("causal-twin-web/1");
  }
  const other = await rowsAs(await signInAs("other@example.org"));
  expect(other.length).toBeGreaterThan(0);
  expect(other.every((r) => r.child_id === theirs)).toBe(true);
  const caregiver = await rowsAs(await signInAs("caregiver@example.org"));
  expect(caregiver.every((r) => r.projection === "active_learnings")).toBe(true);
  expect(await rowsAs(null)).toEqual([]);

  // Signed out: nothing is drawn.
  await page.goto("/causal-twin");
  await expect(page.getByRole("heading", { name: "No links to draw yet" })).toBeVisible();
  await expect(page.locator("section button[data-edge-id]")).toHaveCount(0);

  await page.goto("/sign-in?next=/causal-twin");
  await page.getByLabel("Email").fill("parent@example.org");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3278/causal-twin");
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  const main = page.getByRole("main");
  const select = page.locator("select[data-child-select]");
  if ((await select.inputValue()) !== first) await select.selectOption(first);
  await expect(select).toHaveValue(first);
  await expect(page.locator('[data-sync="live"]')).toBeVisible();

  // Live: the first child's published twin, every link with its full provenance.
  const row = await twinOf(first);
  await expect(page.locator("[data-twin-sequence]")).toHaveAttribute("data-twin-sequence", String(row.last_sequence));
  const edges: any[] = row.state.edges;
  expect(edges.map((e) => e.status).sort()).toEqual(["CANDIDATE", "REFUTED"]);
  for (const edge of edges) {
    await listButton(page, edge.edge_id).click();
    const root = provenance(page, edge.edge_id);
    await expect(root).toHaveAttribute("data-provenance", "full");
    await expect(root.locator("[data-field=complete]")).toHaveText(/Complete/);
    const detail = row.state.provenance.edges.find((e: any) => e.edge_id === edge.edge_id);
    for (const x of detail.experiments) {
      const card = root.locator(`[data-experiment-id="${x.experiment_id}"]`);
      for (const o of x.outcomes) await expect(card.locator(`[data-outcome-id="${o.outcome_id}"]`)).toContainText(o.summary);
    }
    for (const c of detail.counterevidence) await expect(root.locator(`[data-entity-id="${c.entity_id}"]`).first()).toBeVisible();
    await listButton(page, edge.edge_id).click(); // close
  }
  expect(await main.innerText()).not.toMatch(PRIVATE);
  await expect(main).not.toContainText(first);

  // A live append: recorded, but shown only once its projection row arrives.
  const appended = await (await request.post(`${HOST}/__test/append?child=${first}`)).json();
  await expect(listButton(page, appended.hypothesis_id)).toHaveCount(0);
  const republished = await twinOf(first);
  expect(republished.last_sequence).toBeGreaterThan(row.last_sequence);
  deliver(republished);
  await expect(listButton(page, appended.hypothesis_id)).toBeVisible();
  await listButton(page, appended.hypothesis_id).click();
  await expect(provenance(page, appended.hypothesis_id)).toHaveAttribute("data-provenance", "full");
  await expect(provenance(page, appended.hypothesis_id)).toContainText(appended.statement);

  // Disconnect: Reconnecting, the last twin kept; then a resync picks up what was missed.
  const missed = await (await request.post(`${HOST}/__test/append?child=${first}`)).json();
  for (const s of sockets) {
    s.open = false;
    s.ws.close();
  }
  await expect(page.locator('[data-sync="reconnecting"]')).toBeVisible();
  await expect(listButton(page, appended.hypothesis_id)).toBeVisible();
  await expect(page.locator('[data-sync="live"]')).toBeVisible({ timeout: 30_000 });
  await expect(listButton(page, missed.hypothesis_id)).toBeVisible();
  await expect(page.locator("[data-twin-sequence]")).toHaveAttribute(
    "data-twin-sequence",
    String((await twinOf(first)).last_sequence),
  );

  // Child switch: the first child's twin is gone at once; only the second's is drawn.
  const firstStatements = (await twinOf(first)).state.edges.map((e: any) => e.relationship as string);
  await select.selectOption(second);
  for (const id of [appended.hypothesis_id, missed.hypothesis_id, ...edges.map((e) => e.edge_id)]) {
    await expect(listButton(page, id)).toHaveCount(0);
  }
  await expect(page.locator("[data-provenance-for]")).toHaveCount(0);
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  const secondRow = await twinOf(second);
  for (const edge of secondRow.state.edges) await expect(listButton(page, edge.edge_id)).toBeVisible();
  for (const statement of firstStatements) {
    if (!secondRow.state.edges.some((e: any) => e.relationship === statement)) await expect(main).not.toContainText(statement);
  }
  // A late change for the first child is never drawn under the second.
  const late = await (await request.post(`${HOST}/__test/append?child=${first}`)).json();
  const lateRow = await twinOf(first);
  const secondSocket = sockets.filter((s) => s.open && s.topic.endsWith(second)).at(-1)!;
  secondSocket.ws.send(JSON.stringify([secondSocket.join, null, secondSocket.topic, "postgres_changes", { ids: [1], data: {
    schema: "serene", table: "projection_state", type: "UPDATE", commit_timestamp: new Date().toISOString(),
    columns: [], record: lateRow, old_record: {}, errors: [],
  } }]));
  await expect(listButton(page, secondRow.state.edges[0].edge_id)).toBeVisible();
  await expect(listButton(page, late.hypothesis_id)).toHaveCount(0);

  // The browser read projection state and the guardian list, never the ledger.
  const rest = requests.filter((u) => u.includes("/rest/v1/"));
  expect(rest.length).toBeGreaterThan(0);
  expect(rest.every((u) => /\/rest\/v1\/(projection_state|child_guardians)\?/.test(u))).toBe(true);
  const ledger = new RegExp(`${["domain", "events"].join("_")}|__test`); // in parts: see no-ledger.test.ts
  expect(requests.some((u) => ledger.test(u))).toBe(false);
  expect(await (await request.get(`${HOST}/__test/check`)).json()).toEqual({ verified: true });
});
