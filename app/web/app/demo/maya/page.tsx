import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Page } from "@/components/layout/Page";
import { MayaDemoView } from "./MayaDemoView";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Maya demo", robots: { index: false, follow: false } };

export default function MayaDemoPage() {
  if (process.env.SERENE_DEMO_MODE !== "1") notFound();
  return <Page title="Today" lead="DEMO MODE — synthetic Maya scenario" width="wide">
    <MayaDemoView />
  </Page>;
}
