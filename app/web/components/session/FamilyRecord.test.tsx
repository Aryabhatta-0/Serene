import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { LiveInvestigations } from "@/components/investigations/LiveInvestigations";
import recorded from "@/fixtures/synthetic-investigation.json";
import { FakeBackend } from "@/lib/auth/testing";
import { FakeFeed, type Row } from "@/lib/projections/testing";
import { FamilyRecordProvider } from "./FamilyRecord";
import { childLabel, RecordControl } from "./RecordControl";
import { SignInForm } from "./SignInForm";

// The whole signed-in path (Issue #87) through the real provider, record
// control, sign-in form and investigation surface, over the same
// ProjectionSync path the Realtime feed uses (#33). Every account, child and
// row is synthetic.

const PARENT = { email: "parent@example.org", password: "fake-synthetic-only", userId: "00000000-0000-4000-8000-000000000001" };
const OTHER_PARENT = { email: "other@example.org", password: "fake-synthetic-only", userId: "00000000-0000-4000-8000-000000000002" };
const CHILD = recorded.snapshot[0].child_id; // the recorded investigation
const SIBLING = `chd_${"5".repeat(32)}`;
const STRANGER = `chd_${"f".repeat(32)}`; // another family's child

const kernel = (r: Row) => Object.values(r.state)[0] as any;
const firstInv = recorded.snapshot.find((r) => r.projection === "investigations") as Row;
const changes = (recorded.changes as Row[]).filter((r) => r.projection === "investigations");
const QUESTION = kernel(firstInv).question as string;
const SIBLING_QUESTION = "Synthetic: why is bedtime slow?";
const STRANGER_QUESTION = "Synthetic: another family's question";

function rowsFor(child: string, question: string, sequence: number): Row[] {
  const inv = structuredClone(firstInv);
  const [id] = Object.keys(inv.state);
  (inv.state[id] as any).question = question;
  return [{ ...inv, child_id: child, last_sequence: sequence, last_event_hash: sequence.toString(16).padStart(64, "0") }];
}

function setup({ guardians = { [PARENT.userId]: [CHILD, SIBLING], [OTHER_PARENT.userId]: [STRANGER] } } = {}) {
  const feed = new FakeFeed();
  for (const r of recorded.snapshot as Row[]) feed.write(r, { deliver: false });
  for (const r of rowsFor(SIBLING, SIBLING_QUESTION, 3)) feed.write(r, { deliver: false });
  for (const r of rowsFor(STRANGER, STRANGER_QUESTION, 9)) feed.write(r, { deliver: false });
  const backend = new FakeBackend(feed, [PARENT, OTHER_PARENT], guardians);
  render(
    <FamilyRecordProvider backend={backend}>
      <RecordControl next="/today" />
      <SignInForm onSignedIn={() => {}} />
      <LiveInvestigations mode="all" unconnected={<p>Nothing connected</p>} />
    </FamilyRecordProvider>,
  );
  return { feed, backend };
}

async function signIn(account = PARENT) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), account.email);
  await user.type(screen.getByLabelText("Password"), account.password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

const phase = () => document.querySelector("article[data-investigation-id]")?.getAttribute("data-phase");

afterEach(() => sessionStorage.clear());

describe("signed out", () => {
  it("shows the honest unconnected state, subscribes to nothing, and offers sign-in", async () => {
    const { feed, backend } = setup();
    expect(await screen.findByText("Not signed in")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in?next=%2Ftoday");
    expect(screen.getByText("Nothing connected")).toBeInTheDocument();
    expect(feed.subscribers).toBe(0);
    expect(backend.childListCalls).toEqual([]);
  });

  it("a wrong password or an unreachable Serene is said plainly, and nothing connects", async () => {
    const { feed, backend } = setup();
    await signIn({ ...PARENT, password: "wrong" });
    expect(await screen.findByRole("alert")).toHaveTextContent("didn’t match");
    backend.unavailable = true;
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("couldn’t be reached");
    expect(feed.subscribers).toBe(0);
  });
});

describe("signed in", () => {
  it("lists the parent's children, opens the first, and shows its snapshot live", async () => {
    const { feed, backend } = setup();
    await signIn();
    expect(await screen.findByText("Family record connected")).toBeInTheDocument();
    expect(backend.childListCalls).toEqual([PARENT.userId]);
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual([CHILD, SIBLING].sort().map(childLabel)); // ordered by record id
    expect(options).not.toContain(childLabel(STRANGER));
    const selected = [CHILD, SIBLING].sort()[0];
    await act(async () => feed.setStatus("subscribed"));
    const question = selected === CHILD ? QUESTION : SIBLING_QUESTION;
    expect(await screen.findByRole("heading", { level: 2, name: question })).toBeInTheDocument();
    expect(document.querySelector('[data-sync="live"]')).not.toBeNull();
  });

  it("follows a kernel append live, flags a drop, and resyncs on reconnect", async () => {
    const { feed } = setup({ guardians: { [PARENT.userId]: [CHILD] } });
    await signIn();
    await screen.findByText("Family record connected");
    await act(async () => feed.setStatus("subscribed"));
    await waitFor(() => expect(phase()).toBe(kernel(firstInv).phase));

    // A kernel append publishes the next projection row; Realtime delivers it.
    await act(async () => feed.write(changes[0]));
    expect(phase()).toBe(kernel(changes[0]).phase);
    expect(document.querySelector('[data-sync="live"]')).not.toBeNull();

    // The connection drops; later appends reach the table but are not delivered.
    await act(async () => feed.setStatus("closed"));
    expect(document.querySelector('[data-sync="reconnecting"]')).toHaveTextContent("may be out of date");
    for (const change of changes.slice(1)) feed.write(change, { deliver: false });
    expect(phase()).toBe(kernel(changes[0]).phase);

    // Reconnecting re-reads the snapshot: the missed changes appear.
    const before = feed.snapshotCalls;
    await act(async () => feed.setStatus("subscribed"));
    await waitFor(() => expect(phase()).toBe(kernel(changes[changes.length - 1]).phase));
    expect(feed.snapshotCalls).toBe(before + 1);
    expect(document.querySelector('[data-sync="live"]')).not.toBeNull();
  });

  it("switching child shows only that child's record, and ignores the previous child's late rows", async () => {
    const { feed } = setup();
    const user = await signIn();
    const select = await screen.findByRole("combobox");
    await user.selectOptions(select, CHILD);
    await act(async () => feed.setStatus("subscribed"));
    expect(await screen.findByRole("heading", { level: 2, name: QUESTION })).toBeInTheDocument();

    feed.holdSnapshots = true; // the previous child's read is still in flight at the switch
    await user.selectOptions(select, SIBLING);
    await act(async () => feed.setStatus("subscribed"));
    expect(screen.queryByText(QUESTION)).toBeNull();
    feed.holdSnapshots = false;
    await act(async () => feed.setStatus("subscribed"));
    expect(await screen.findByRole("heading", { level: 2, name: SIBLING_QUESTION })).toBeInTheDocument();

    // A late change for the first child (or another family's) never shows here.
    await act(async () => feed.emit(changes[0]));
    await act(async () => feed.emit(rowsFor(STRANGER, STRANGER_QUESTION, 99)[0]));
    expect(screen.queryByText(QUESTION)).toBeNull();
    expect(screen.queryByText(STRANGER_QUESTION)).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: SIBLING_QUESTION })).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem("serene.selected-child")!)).toEqual({
      userId: PARENT.userId,
      childId: SIBLING,
    });
  });

  it("a stored choice of a child this parent cannot see is never opened", async () => {
    sessionStorage.setItem("serene.selected-child", JSON.stringify({ userId: PARENT.userId, childId: STRANGER }));
    const { feed } = setup();
    await signIn();
    await screen.findByText("Family record connected");
    await act(async () => feed.setStatus("subscribed"));
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).not.toBe(STRANGER);
    expect(screen.queryByText(STRANGER_QUESTION)).toBeNull();
  });

  it("an account with no children sees that, and no record", async () => {
    const { feed } = setup({ guardians: {} });
    await signIn();
    expect(await screen.findByText("No child linked")).toBeInTheDocument();
    expect(screen.getByText("No child linked to this account")).toBeInTheDocument();
    expect(feed.subscribers).toBe(0);
  });

  it("a failed child lookup shows nothing rather than guessing", async () => {
    const { feed, backend } = setup();
    backend.failChildren = true;
    await signIn();
    expect(await screen.findByText(/couldn’t be found just now/)).toBeInTheDocument();
    expect(feed.subscribers).toBe(0);
  });
});

describe("leaving", () => {
  it("an expired session removes the record at once and says so", async () => {
    const { feed, backend } = setup({ guardians: { [PARENT.userId]: [CHILD] } });
    await signIn();
    await screen.findByText("Family record connected");
    await act(async () => feed.setStatus("subscribed"));
    expect(await screen.findByRole("heading", { level: 2, name: QUESTION })).toBeInTheDocument();

    await act(async () => backend.expire());
    expect(screen.getByText("Your session ended", { selector: "h2" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in again" })).toBeInTheDocument();
    expect(screen.queryByText(QUESTION)).toBeNull();
    expect(feed.subscribers).toBe(0);
    expect(sessionStorage.getItem("serene.selected-child")).toBeNull();
  });

  it("signing out is a sign-out, not an expiry, and forgets the child", async () => {
    const { feed } = setup({ guardians: { [PARENT.userId]: [CHILD] } });
    const user = await signIn();
    await screen.findByText("Family record connected");
    await act(async () => feed.setStatus("subscribed"));
    await screen.findByRole("heading", { level: 2, name: QUESTION });
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("Not signed in")).toBeInTheDocument();
    expect(screen.queryByText("Your session ended")).toBeNull();
    expect(screen.queryByText(QUESTION)).toBeNull();
    expect(feed.subscribers).toBe(0);
    expect(sessionStorage.getItem("serene.selected-child")).toBeNull();
  });

  it("another account signing in never inherits the previous account's child", async () => {
    const { feed, backend } = setup();
    await signIn();
    await screen.findByText("Family record connected");
    await act(async () => feed.setStatus("subscribed"));
    await act(async () => backend.switchUser(OTHER_PARENT.userId));
    await waitFor(() => expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([childLabel(STRANGER)]));
    await act(async () => feed.setStatus("subscribed"));
    expect(await screen.findByRole("heading", { level: 2, name: STRANGER_QUESTION })).toBeInTheDocument();
    expect(screen.queryByText(QUESTION)).toBeNull();
    expect(screen.queryByText(SIBLING_QUESTION)).toBeNull();
  });
});
