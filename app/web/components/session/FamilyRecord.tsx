"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { supabaseBackend, type FamilyBackend, type SignInResult } from "@/lib/auth/backend";
import { browserClient } from "@/lib/auth/client";
import { forgetChild, recallChild, rememberChild, tabStore } from "@/lib/auth/selection";
import { nextSession, type SessionState } from "@/lib/auth/session";
import { supabaseConfig } from "@/lib/projections/config";
import type { ProjectionFeed } from "@/lib/projections/sync";

// The signed-in family record (Issue #87): who is signed in, which of their
// children is open, and the live projection feed (#33) for that child. A
// surface gets a feed and a child id only when all three are settled; in every
// other state it gets neither, and shows its honest "not connected" state.

export type ChildList = { status: "loading" } | { status: "error" } | { status: "ready"; ids: readonly string[] };

export type FamilyRecordState =
  | Exclude<SessionState, { status: "signed-in" }>
  | { status: "signed-in"; children: ChildList; childId: string | null };

export type FamilyRecord = FamilyRecordState & {
  /** Present only when signed in with a child chosen. */
  live: { feed: ProjectionFeed; childId: string } | null;
  signIn(email: string, password: string): Promise<SignInResult>;
  signOut(): Promise<void>;
  selectChild(childId: string): void;
};

const UNAVAILABLE: SignInResult = { ok: false, reason: "unavailable" };

const Context = createContext<FamilyRecord>({
  status: "unconfigured",
  live: null,
  signIn: async () => UNAVAILABLE,
  signOut: async () => {},
  selectChild: () => {},
});

export function useFamilyRecord(): FamilyRecord {
  return useContext(Context);
}

type Props = {
  /** Test builds only: a stand-in backend. Omitted, the configured Supabase project is used. */
  backend?: FamilyBackend;
  children: ReactNode;
};

export function FamilyRecordProvider({ backend: given, children }: Props) {
  // Configuration is fixed at build time, so the server and the first client
  // render agree: "loading" when configured, "unconfigured" when not.
  const configured = given !== undefined || supabaseConfig() !== null;
  const [backend, setBackend] = useState<FamilyBackend | null>(given ?? null);
  const [session, setSession] = useState<SessionState>(configured ? { status: "loading" } : { status: "unconfigured" });
  const [kids, setKids] = useState<ChildList>({ status: "loading" });
  const [childId, setChildId] = useState<string | null>(null);
  const signingOut = useRef(false);

  useEffect(() => {
    if (given) return setBackend(given);
    const config = supabaseConfig();
    setBackend(config ? supabaseBackend(browserClient(config)) : null);
  }, [given]);

  useEffect(() => {
    if (!backend) return;
    return backend.onAuthChange((snapshot) => {
      const intended = signingOut.current;
      if (!snapshot) signingOut.current = false;
      setSession((prev) => nextSession(prev, snapshot, intended));
    });
  }, [backend]);

  const userId = session.status === "signed-in" ? session.userId : null;
  useEffect(() => {
    // A new user (or nobody) never inherits the previous list or choice.
    setKids({ status: "loading" });
    setChildId(null);
    if (!backend || !userId) return;
    let current = true;
    backend.listChildren(userId).then(
      (ids) => {
        if (!current) return;
        setKids({ status: "ready", ids });
        setChildId(recallChild(tabStore(), userId, ids));
      },
      () => current && setKids({ status: "error" }),
    );
    return () => {
      current = false;
    };
  }, [backend, userId]);

  useEffect(() => {
    if (session.status === "signed-out" || session.status === "expired") forgetChild(tabStore());
  }, [session.status]);

  const signIn = useCallback(
    (email: string, password: string) => (backend ? backend.signIn(email, password) : Promise.resolve(UNAVAILABLE)),
    [backend],
  );
  const signOut = useCallback(async () => {
    if (!backend) return;
    signingOut.current = true;
    forgetChild(tabStore());
    await backend.signOut();
  }, [backend]);
  const selectChild = useCallback(
    (id: string) => {
      // Only a child RLS listed for this user can be opened.
      if (!userId || kids.status !== "ready" || !kids.ids.includes(id)) return;
      rememberChild(tabStore(), userId, id);
      setChildId(id);
    },
    [userId, kids],
  );

  const value = useMemo<FamilyRecord>(() => {
    const actions = { signIn, signOut, selectChild };
    if (session.status !== "signed-in") return { ...session, live: null, ...actions };
    const chosen = kids.status === "ready" && childId !== null && kids.ids.includes(childId) ? childId : null;
    return {
      status: "signed-in",
      children: kids,
      childId: chosen,
      live: backend && chosen ? { feed: backend.feed, childId: chosen } : null,
      ...actions,
    };
  }, [session, kids, childId, backend, signIn, signOut, selectChild]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}
