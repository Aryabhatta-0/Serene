"use client";

import { useState } from "react";
import { ExperimentsView } from "@/components/experiments/ExperimentsView";
import type { ApprovalCommand, ApprovalTransport } from "@/lib/experiments/approval";
import type { ExperimentsSource } from "@/lib/experiments/source";

// TEST BUILDS ONLY (imported only by page.fixture.tsx). A scripted stand-in
// for the kernel transport, so the browser tests can check exactly which
// command the surface sends and how it shows each kind of answer. The answer
// is chosen by the test with `?answer=granted|refused|unreadable|offline`;
// nothing here reaches Serene, and the experiments' stages never change.
const ANSWERS: Record<string, unknown> = {
  granted: { outcome: "APPROVAL_GRANTED", reason_codes: [] },
  declined: { outcome: "APPROVAL_REJECTED", reason_codes: [] },
  refused: { outcome: "REFUSED", reason_codes: ["APPROVAL_EXPIRED"] },
  unreadable: { outcome: "PROBABLY_FINE" },
};

export function FixtureExperiments({ source }: { source: ExperimentsSource }) {
  const [sent, setSent] = useState<ApprovalCommand[]>([]);
  const decide: ApprovalTransport = async (command) => {
    setSent((all) => [...all, command]);
    const answer = new URLSearchParams(window.location.search).get("answer") ?? "refused";
    if (answer === "offline") throw new Error("offline");
    return ANSWERS[answer] ?? ANSWERS.refused;
  };
  return (
    <>
      <ExperimentsView source={source} decide={decide} />
      <output hidden data-sent-commands={JSON.stringify(sent)} />
    </>
  );
}
