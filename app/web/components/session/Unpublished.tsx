"use client";

import type { ReactNode } from "react";
import { useFamilyRecord } from "./FamilyRecord";

// For a surface whose view the kernel does not publish to the web yet: with
// nobody signed in it shows the surface's own empty state; signed in with a
// child chosen, it says plainly that this view is not available here, rather
// than implying the child has nothing recorded.
export function Unpublished({ unconnected, signedIn }: { unconnected: ReactNode; signedIn: ReactNode }) {
  const { live } = useFamilyRecord();
  return <>{live ? signedIn : unconnected}</>;
}
