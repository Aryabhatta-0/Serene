"use client";

import { useId, type ReactNode } from "react";
import { RecordStatus } from "@/components/shell/RecordStatus";
import statusStyles from "@/components/shell/RecordStatus.module.css";
import { useFamilyRecord } from "./FamilyRecord";
import styles from "./Session.module.css";

/** Children carry no names in Serene; each is shown by the end of its record id. */
export function childLabel(childId: string): string {
  return `Child ·${childId.slice(-4)}`;
}

function signInHref(next: string): string {
  return `/sign-in?next=${encodeURIComponent(next)}`;
}

// The record status for surfaces that read the signed-in family record (Issue
// #87): who is signed in, which child is open, and the way to change either.
// It always says what is connected; it never implies data that isn't there.
export function RecordControl({ next }: { next: string }) {
  const record = useFamilyRecord();
  const selectId = useId();

  switch (record.status) {
    case "unconfigured":
      return <RecordStatus />;
    case "loading":
      return <Status title="Checking sign-in" detail="Nothing is shown until Serene knows who you are." />;
    case "signed-out":
      return (
        <Status title="Not signed in" detail="Sign in to see your family’s record.">
          <a className="button" href={signInHref(next)}>
            Sign in
          </a>
        </Status>
      );
    case "expired":
      return (
        <Status title="Your session ended" detail="Sign in again to continue. Nothing is shown meanwhile." live>
          <a className="button" href={signInHref(next)}>
            Sign in again
          </a>
        </Status>
      );
  }

  const signOut = (
    <button type="button" className="button" onClick={() => void record.signOut()}>
      Sign out
    </button>
  );
  const kids = record.children;
  if (kids.status === "loading") {
    return <Status title="Signed in" detail="Finding your family’s record…" />;
  }
  if (kids.status === "error") {
    return (
      <Status title="Signed in" detail="Your family’s record couldn’t be found just now, so nothing is shown." live>
        {signOut}
      </Status>
    );
  }
  if (kids.ids.length === 0) {
    return (
      <Status title="No child linked" detail="This account is not a parent of any child in Serene yet." live>
        {signOut}
      </Status>
    );
  }
  return (
    <Status title="Family record connected" detail="Showing one child’s record at a time." connected>
      <span className={styles.field}>
        <label htmlFor={selectId}>Child</label>
        <select
          id={selectId}
          className={styles.select}
          value={record.childId ?? ""}
          onChange={(e) => record.selectChild(e.target.value)}
          data-child-select
        >
          {kids.ids.map((id) => (
            <option key={id} value={id}>
              {childLabel(id)}
            </option>
          ))}
        </select>
      </span>
      {signOut}
    </Status>
  );
}

type StatusProps = {
  title: string;
  detail: string;
  /** Solid ring: a record is connected. Dotted: nothing is. */
  connected?: boolean;
  /** Announce changes (the session ending, nothing linked) to assistive tech. */
  live?: boolean;
  children?: ReactNode;
};

function Status({ title, detail, connected = false, live = false, children }: StatusProps) {
  return (
    <div className={styles.record} data-record={title} role={live ? "status" : undefined}>
      <p className={statusStyles.status}>
        <svg
          className={connected ? `${statusStyles.ring} ${styles.connected}` : statusStyles.ring}
          viewBox="0 0 16 16"
          aria-hidden="true"
          focusable="false"
        >
          <circle cx="8" cy="8" r="6" />
        </svg>
        <span>
          <span className={statusStyles.title}>{title}</span>
          <span className={statusStyles.detail}>{detail}</span>
        </span>
      </p>
      {children ? <div className={styles.actions}>{children}</div> : null}
    </div>
  );
}
