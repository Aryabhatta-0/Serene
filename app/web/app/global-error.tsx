"use client";

import { useEffect } from "react";

// Last-resort boundary for failures in the root layout itself, where the
// shell, fonts and tokens may not be available. Kept deliberately plain.
export default function GlobalError({
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
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", lineHeight: 1.5 }}>
        <h1>Serene couldn’t be shown</h1>
        <p>Showing a page never changes your family’s record.</p>
        <button type="button" onClick={reset}>
          Try again
        </button>
      </body>
    </html>
  );
}
