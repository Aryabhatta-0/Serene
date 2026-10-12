"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { safeNext } from "@/lib/auth/next";
import { useFamilyRecord } from "./FamilyRecord";
import styles from "./Session.module.css";

type Step = { kind: "idle" } | { kind: "sending" } | { kind: "refused" } | { kind: "unavailable" };

const MESSAGES = {
  refused: "That email and password didn’t match an account. Nothing was changed.",
  unavailable: "Serene couldn’t be reached, so you are not signed in. Try again in a moment.",
} as const;

// Email and password sign-in through Supabase Auth (Issue #87). The form
// reports only what Supabase answered; it never guesses at a session. Once
// signed in it goes on to the surface the parent came from.
export function SignInForm({ next, onSignedIn }: { next?: string | null; onSignedIn?: (href: string) => void }) {
  const record = useFamilyRecord();
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const errorId = useId();
  const destination = safeNext(next);

  useEffect(() => {
    if (record.status !== "signed-in") return;
    if (onSignedIn) onSignedIn(destination);
    else window.location.assign(destination);
  }, [record.status, destination, onSignedIn]);

  if (record.status === "unconfigured") {
    return (
      <p className={styles.message} role="note">
        Sign-in isn’t set up for this copy of Serene, so no family record can be shown.
      </p>
    );
  }
  if (record.status === "signed-in") {
    return (
      <p className={styles.message} role="status">
        You’re signed in. <a href={destination}>Continue</a>
      </p>
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setStep({ kind: "sending" });
    const result = await record.signIn(String(data.get("email") ?? ""), String(data.get("password") ?? ""));
    if (!result.ok) setStep({ kind: result.reason === "credentials" ? "refused" : "unavailable" });
    // On success the session arrives through the family record and the effect above moves on.
  }

  const failed = step.kind === "refused" || step.kind === "unavailable";
  return (
    <form className={styles.form} onSubmit={submit} aria-describedby={failed ? errorId : undefined} data-sign-in>
      {record.status === "expired" ? (
        <p className={styles.message} role="status">
          Your session ended, so nothing from your family’s record is shown. Sign in again to continue.
        </p>
      ) : null}
      <label>
        <span className={styles.label}>Email</span>
        <input className={styles.input} name="email" type="email" autoComplete="username" required />
      </label>
      <label>
        <span className={styles.label}>Password</span>
        <input className={styles.input} name="password" type="password" autoComplete="current-password" required />
      </label>
      {failed ? (
        <p id={errorId} className={styles.message} role="alert">
          {MESSAGES[step.kind]}
        </p>
      ) : null}
      <button type="submit" className="button" disabled={step.kind === "sending" || record.status === "loading"}>
        {step.kind === "sending" ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
