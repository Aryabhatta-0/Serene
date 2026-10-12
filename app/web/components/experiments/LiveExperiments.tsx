"use client";

import { useMemo } from "react";
import { useFamilyRecord } from "@/components/session/FamilyRecord";
import type { ExperimentsSource } from "@/lib/experiments/source";
import { webApprovalTransport } from "@/lib/experiments/transport";
import { ExperimentsView } from "./ExperimentsView";

// The Experiments surface with the real decision transport (Issue #84): a
// parent can decide only while signed in with a child chosen (#87), and only
// for that child. The decision goes to the kernel; the stage shown changes
// only when the kernel's record does.
export function LiveExperiments({ source }: { source: ExperimentsSource }) {
  const { live, accessToken } = useFamilyRecord();
  const childId = live?.childId ?? null;
  const decide = useMemo(() => (childId ? webApprovalTransport(childId, accessToken) : null), [childId, accessToken]);
  return <ExperimentsView source={source} decide={decide} />;
}
