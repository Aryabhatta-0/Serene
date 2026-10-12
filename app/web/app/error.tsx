"use client";

import { useEffect } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";

export default function SurfaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Serene view error"); // Exception messages/stacks may contain private input.
  }, [error]);

  return (
    <Page title="This view couldn’t be shown" lead="Something went wrong while drawing this page." width="reading">
      <EmptyState
        title="Nothing was changed"
        tone="stopped"
        actions={
          <button type="button" className="button" onClick={reset}>
            Try again
          </button>
        }
      >
        <p>Showing a page never changes your family’s record. You can try again.</p>
      </EmptyState>
    </Page>
  );
}
