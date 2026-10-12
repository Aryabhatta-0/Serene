import type { Metadata } from "next";
import { FixtureFamily } from "./FixtureFamily";

// TEST BUILDS ONLY. Routed only when SERENE_FIXTURE_ROUTES=1 (next.config.mjs);
// a normal build has no such page. A synthetic account and synthetic children
// stand in for Supabase; nothing here describes a real child.
export const metadata: Metadata = {
  title: "Signed-in Today (synthetic fixture)",
  robots: { index: false, follow: false },
};

export default function SessionFixturePage() {
  return <FixtureFamily />;
}
