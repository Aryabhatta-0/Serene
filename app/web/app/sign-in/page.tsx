import type { Metadata } from "next";
import { Page } from "@/components/layout/Page";
import { SignInForm } from "@/components/session/SignInForm";

export const metadata: Metadata = { title: "Sign in", robots: { index: false, follow: false } };

// Supabase Auth sign-in for parents (Issue #87). After it, Today and
// Investigations read the signed-in parent's child's record live.
export default function SignInPage({ searchParams }: { searchParams: { next?: string | string[] } }) {
  const next = typeof searchParams.next === "string" ? searchParams.next : null;
  return (
    <Page
      title="Sign in"
      lead="Sign in to see your family’s record. Serene shows only the children you are a parent of."
      width="reading"
      status={null}
    >
      <SignInForm next={next} />
    </Page>
  );
}
