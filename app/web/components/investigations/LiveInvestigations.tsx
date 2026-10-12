"use client";

import type { ReactNode } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { useFamilyRecord } from "@/components/session/FamilyRecord";
import { InvestigationSurface } from "./InvestigationSurface";

type Props = {
  mode: "today" | "all";
  /** What to show while nothing is connected (each surface words its own). */
  unconnected: ReactNode;
};

// Today and Investigations on the signed-in family record (Issue #87): the
// projection feed (#33) and the chosen child come from the session, and only
// when both are settled. Switching child remounts the surface, so nothing of
// one child's record is ever shown under another's.
export function LiveInvestigations({ mode, unconnected }: Props) {
  const record = useFamilyRecord();
  if (record.live) {
    return (
      <InvestigationSurface
        key={record.live.childId}
        feed={record.live.feed}
        childId={record.live.childId}
        mode={mode}
        unconnected={unconnected}
      />
    );
  }
  if (record.status === "expired") {
    return (
      <EmptyState title="Your session ended">
        <p>Nothing from your family’s record is shown until you sign in again. Nothing in it was changed.</p>
      </EmptyState>
    );
  }
  if (record.status === "signed-in" && record.children.status === "ready" && record.children.ids.length === 0) {
    return (
      <EmptyState title="No child linked to this account">
        <p>Serene shows a record only to a child’s parent. Nothing from any other family is shown.</p>
      </EmptyState>
    );
  }
  return <>{unconnected}</>;
}
