import type { Metadata } from "next";
import { Landing } from "@/components/landing/Landing";

export const metadata: Metadata = { title: { absolute: "Serene" } };

// The front door: the bloom, and the way into the five surfaces.
export default function Home() {
  return <Landing />;
}
