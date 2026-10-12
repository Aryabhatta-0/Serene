// Which child's record is open, kept for this browser tab only (Issue #87).
// The stored choice is a hint, never an authority: it is restored only for the
// same signed-in user, and only if that child is in the list RLS returned
// right now. Signing out, or a session ending, forgets it.

const KEY = "serene.selected-child";

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function tabStore(): Store | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null; // storage blocked: the choice simply isn't remembered
  }
}

export function recallChild(store: Store | null, userId: string, children: readonly string[]): string | null {
  try {
    const saved = JSON.parse(store?.getItem(KEY) ?? "null") as { userId?: unknown; childId?: unknown } | null;
    if (saved && saved.userId === userId && typeof saved.childId === "string" && children.includes(saved.childId)) {
      return saved.childId;
    }
  } catch {
    // unreadable: fall through to the default
  }
  return children[0] ?? null;
}

export function rememberChild(store: Store | null, userId: string, childId: string): void {
  try {
    store?.setItem(KEY, JSON.stringify({ userId, childId }));
  } catch {
    // not remembered; the choice still holds for this page
  }
}

export function forgetChild(store: Store | null): void {
  try {
    store?.removeItem(KEY);
  } catch {
    // nothing to forget
  }
}
