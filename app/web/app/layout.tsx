import "./globals.css";
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import { BLOOM_SCRIPT, BloomDirector } from "@/components/brand/BloomDirector";
import { PETAL_SRC } from "@/components/brand/Hellebore";
import { FamilyRecordProvider } from "@/components/session/FamilyRecord";
import { AppShell } from "@/components/shell/AppShell";

// Self-hosted and preloaded, with a metric-matched fallback so the swap does
// not shift layout. Latin covers the interface copy; other scripts fall back.
const atkinson = localFont({
  src: "../node_modules/@fontsource-variable/atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-wght-normal.woff2",
  weight: "200 800",
  variable: "--font-atkinson",
  display: "swap",
});

// The display voice: wide geometric capitals for titles, the wordmark and
// tracked labels. Reading text stays in Atkinson.
const montserrat = localFont({
  src: "../node_modules/@fontsource-variable/montserrat/files/montserrat-latin-wght-normal.woff2",
  weight: "100 900",
  variable: "--font-montserrat",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Serene", template: "%s · Serene" },
  description: "A self-correcting family intelligence agent.",
};

// Mirrors --ground in globals.css; the sheet is always light.
export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#e0dfd8",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The bloom script marks <html> before hydration; React must not object.
    <html
      lang="en"
      className={`${atkinson.variable} ${montserrat.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: BLOOM_SCRIPT }} />
        {/* Every flower is built from this one petal; fetch it before the
            bloom starts to open. */}
        <link rel="preload" as="image" href={PETAL_SRC} type="image/webp" />
      </head>
      <body>
        <BloomDirector />
        <FamilyRecordProvider>
          <AppShell>{children}</AppShell>
        </FamilyRecordProvider>
      </body>
    </html>
  );
}
