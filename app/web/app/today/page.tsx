import type { Metadata } from "next";
import { LiveInvestigations } from "@/components/investigations/LiveInvestigations";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";
import { LineKey, type LineKeyEntry } from "@/components/notation/LineKey";
import { RecordControl } from "@/components/session/RecordControl";
import { DemoInvestigations } from "@/components/demo/DemoInvestigations";
import { DemoNotice } from "@/components/demo/DemoNotice";

export const metadata: Metadata = { title: "Today" };
export const dynamic = "force-dynamic";

const CERTAINTY_KEY: readonly LineKeyEntry[] = [
  {
    certainty: "unknown",
    term: "Dotted: a possibility",
    description: "Something Serene is considering. Nothing supports it yet.",
  },
  {
    certainty: "observed",
    term: "Dashed: observed",
    description: "Seen on more than one occasion, but not yet tested.",
  },
  {
    certainty: "tested",
    term: "Solid: tested here",
    description: "Supported by an experiment you approved, in your family’s own context.",
  },
];

export default function TodayPage() {
  const demo = process.env.SERENE_DEMO_MODE === "1";
  return (
    <Page
      title="Today"
      question="What matters now?"
      lead="What Serene is working on, what it doesn’t know yet, and what it would do next, each with how sure it is."
      status={<RecordControl next="/today" />}
    >
      {/* The current investigation, from the `investigations` projection over the
          Realtime projection path (#33), for the signed-in parent's chosen child
          (#87). Signed out, unconfigured or with no child, Today stays honestly empty. */}
      {demo ? <DemoNotice /> : null}
      {demo ? (
        <DemoInvestigations mode="today" />
      ) : (
        <LiveInvestigations
          mode="today"
          unconnected={
            <EmptyState title="Nothing to review today">
              <p>
                No family record is connected, so there is nothing to report. When
                there is, Today leads with the one question Serene is working on and
                what it will do next, with anything that needs you beside it.
              </p>
            </EmptyState>
          }
        />
      )}
      <LineKey title="How Serene shows what it’s sure of" entries={CERTAINTY_KEY} />
    </Page>
  );
}
