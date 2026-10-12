import type { ProjectionFeed } from "@/lib/projections/sync";
import type { AuthSnapshot, FamilyBackend, SignInResult } from "./backend";

// A stand-in for Supabase Auth plus the guardian registry, for unit tests and
// test-build fixture pages only (never imported by a shipped page). Accounts,
// guardianship and the feed are all synthetic. `expire()` ends the session the
// way a refused token refresh does: without the parent signing out.

export type Account = { email: string; password: string; userId: string };

export class FakeBackend implements FamilyBackend {
  session: AuthSnapshot = null;
  failChildren = false;
  unavailable = false;
  childListCalls: string[] = [];
  private listeners = new Set<(session: AuthSnapshot) => void>();

  constructor(
    readonly feed: ProjectionFeed,
    private readonly accounts: readonly Account[],
    /** userId -> the children that user is a parent of. */
    readonly guardians: Record<string, readonly string[]>,
  ) {}

  onAuthChange(listener: (session: AuthSnapshot) => void): () => void {
    this.listeners.add(listener);
    // Supabase reports the stored session asynchronously after subscribing.
    queueMicrotask(() => this.listeners.has(listener) && listener(this.session));
    return () => {
      this.listeners.delete(listener);
    };
  }

  async signIn(email: string, password: string): Promise<SignInResult> {
    if (this.unavailable) return { ok: false, reason: "unavailable" };
    const account = this.accounts.find((a) => a.email === email && a.password === password);
    if (!account) return { ok: false, reason: "credentials" };
    this.set({ userId: account.userId });
    return { ok: true };
  }

  async signOut(): Promise<void> {
    this.set(null);
  }

  /** The session ends without a sign-out (its refresh was refused). */
  expire(): void {
    this.set(null);
  }

  /** Another account signs in in this browser. */
  switchUser(userId: string): void {
    this.set({ userId });
  }

  async listChildren(userId: string): Promise<string[]> {
    this.childListCalls.push(userId);
    if (this.failChildren) throw new Error("registry unavailable");
    return [...(this.guardians[userId] ?? [])].sort();
  }

  private set(session: AuthSnapshot): void {
    this.session = session;
    for (const listener of [...this.listeners]) listener(session);
  }
}
