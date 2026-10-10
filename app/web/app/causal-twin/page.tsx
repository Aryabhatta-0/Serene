import type { Metadata } from "next";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";
import { LineKey, type LineKeyEntry } from "@/components/notation/LineKey";

export const metadata: Metadata = { title: "Causal Twin" };

const LINK_KEY: readonly LineKeyEntry[] = [
  {
    certainty: "unknown",
    term: "Hypothesis",
    description: "A link Serene thinks is possible. Nothing supports it yet.",
  },
  {
    certainty: "observed",
    term: "Observed",
    description: "Supported by what has been seen, not by a test.",
  },
  {
    certainty: "tested",
    term: "Tested in context",
    description: "Supported by an experiment, and only within the situations it was tested in.",
  },
  {
    certainty: "refuted",
    term: "Refuted",
    description: "Tested and contradicted. Kept on the map so the correction stays visible.",
  },
];

export default function CausalTwinPage() {
  return (
    <Page
      title="Causal Twin"
      lead="A map of what may influence what in your child’s days, drawn by how firmly each link is known."
    >
      <EmptyState title="No links to draw yet">
        <p>
          The map is built only from recorded evidence. Until there is some, it
          stays empty rather than guessing.
        </p>
      </EmptyState>
      <LineKey title="How links will be drawn" entries={LINK_KEY} />
    </Page>
  );
}
