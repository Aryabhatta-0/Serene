import Link from "next/link";
import { EmptyState } from "@/components/layout/EmptyState";
import { Page } from "@/components/layout/Page";

export default function NotFound() {
  return (
    <Page title="Page not found" lead="There is no Serene surface at this address.">
      <EmptyState title="Nothing here">
        <p>
          The address may be mistyped, or the page may have moved.{" "}
          <Link href="/today">Go to Today</Link>.
        </p>
      </EmptyState>
    </Page>
  );
}
