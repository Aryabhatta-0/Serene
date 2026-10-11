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
    console.error(error);
  }, [error]);

  return (
    <Page title="This view couldn’t be shown" lead="Something went wrong while drawing this page.">
      <EmptyState title="Nothing was changed">
        <p>Showing a page never changes your family’s record. You can try again.</p>
        <p>
          <button type="button" className="button" onClick={reset}>
            Try again
          </button>
        </p>
      </EmptyState>
    </Page>
  );
}
