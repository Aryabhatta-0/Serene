import "@fontsource-variable/atkinson-hyperlegible-next";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: { default: "Serene", template: "%s · Serene" },
  description: "A self-correcting family intelligence agent.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eef2ee" },
    { media: "(prefers-color-scheme: dark)", color: "#111a19" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
