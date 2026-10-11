import type { Metadata } from "next";
import { InvestigationSurface } from "@/components/investigations/InvestigationSurface";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";
import { LineKey, type LineKeyEntry } from "@/components/notation/LineKey";

export const metadata: Metadata = { title: "Today" };

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
  return (
    <Page
      title="Today"
      lead="What Serene is working on, what it doesn’t know yet, and what it would do next, each with how sure it is."
    >
      {/* The current investigation, from the `investigations` projection over the
          Realtime projection path (#33). Web sign-in is not built yet (#84), so
          no feed is passed and Today stays honestly empty. */}
      <InvestigationSurface
        feed={null}
        childId={null}
        mode="today"
        unconnected={
          <EmptyState title="Nothing to review today">
            <p>
              No family record is connected, so there is nothing to report. When
              there is, each item will show the evidence behind it and how firmly
              it is held.
            </p>
          </EmptyState>
        }
      />
      <LineKey title="How Serene shows what it’s sure of" entries={CERTAINTY_KEY} />
    </Page>
  );
}
