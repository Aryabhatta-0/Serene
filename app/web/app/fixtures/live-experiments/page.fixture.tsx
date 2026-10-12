import type { Metadata } from "next";
import { FixtureLiveExperiments } from "./FixtureLiveExperiments";

// TEST BUILDS ONLY. Routed only when SERENE_FIXTURE_ROUTES=1 (next.config.mjs);
// a normal build has no such page. Synthetic account, child and experiments.
export const metadata: Metadata = {
  title: "Signed-in Experiments (synthetic fixture)",
  robots: { index: false, follow: false },
};

export default function LiveExperimentsFixturePage() {
  return <FixtureLiveExperiments />;
}
