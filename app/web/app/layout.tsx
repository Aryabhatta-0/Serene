import "./globals.css";
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";

// Self-hosted and preloaded, with a metric-matched fallback so the swap does
// not shift layout. Latin covers the interface copy; other scripts fall back.
const atkinson = localFont({
  src: "../node_modules/@fontsource-variable/atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-wght-normal.woff2",
  weight: "200 800",
  variable: "--font-atkinson",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Serene", template: "%s · Serene" },
  description: "A self-correcting family intelligence agent.",
};

// Mirrors --ground in globals.css for each colour scheme.
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eef2ee" },
    { media: "(prefers-color-scheme: dark)", color: "#111a19" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={atkinson.variable}>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
