import type { SupabaseClient } from "@supabase/supabase-js";
import { supabaseProjectionFeed } from "@/lib/projections/supabase";
import type { ProjectionFeed } from "@/lib/projections/sync";

// Everything the web app needs from Supabase to show one family's record
// (Issue #87): who is signed in, which children they are a parent of, and the
// projection feed (#33). `supabaseBackend` is the real one; browser tests
// supply a stand-in with the same shape.

/** Who is signed in, or nobody. Only the opaque Supabase user id is kept. */
export type AuthSnapshot = { userId: string } | null;

export type SignInResult = { ok: true } | { ok: false; reason: "credentials" | "unavailable" };

export interface FamilyBackend {
  /** Calls back with the stored session (if any), then on every change. Returns an unsubscribe. */
  onAuthChange(listener: (session: AuthSnapshot) => void): () => void;
  signIn(email: string, password: string): Promise<SignInResult>;
  signOut(): Promise<void>;
  /** The children this user is a parent of, as RLS shows them. */
  listChildren(userId: string): Promise<string[]>;
  feed: ProjectionFeed;
}

const CHILD_ID = /^chd_[0-9a-f]{32}$/;

export function supabaseBackend(client: SupabaseClient): FamilyBackend {
  return {
    onAuthChange(listener) {
      const { data } = client.auth.onAuthStateChange((_event, session) => {
        listener(session?.user ? { userId: session.user.id } : null);
      });
      return () => data.subscription.unsubscribe();
    },
    async signIn(email, password) {
      try {
        const { error } = await client.auth.signInWithPassword({ email, password });
        if (!error) return { ok: true };
        // A wrong email or password is a 400; anything else is Serene being unreachable.
        return { ok: false, reason: error.status === 400 ? "credentials" : "unavailable" };
      } catch {
        return { ok: false, reason: "unavailable" };
      }
    },
    async signOut() {
      // This browser only; supabase-js clears the stored session even offline.
      await client.auth.signOut({ scope: "local" });
    },
    async listChildren(userId) {
      // serene.child_guardians (#8): RLS returns only the signed-in user's own
      // rows. The filters repeat that, and keep parents only: a caregiver's
      // grant covers active learnings, not these surfaces.
      const { data, error } = await client
        .schema("serene")
        .from("child_guardians")
        .select("child_id")
        .eq("user_id", userId)
        .eq("role", "PARENT");
      if (error) throw new Error(error.message);
      const ids = (data ?? []).map((row: { child_id?: unknown }) => row.child_id);
      if (!ids.every((id): id is string => typeof id === "string" && CHILD_ID.test(id))) {
        throw new Error("a child id did not pass its checks");
      }
      return [...new Set(ids)].sort();
    },
    feed: supabaseProjectionFeed(client),
  };
}
