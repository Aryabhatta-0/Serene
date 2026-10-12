"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { MobileMenu } from "./MobileMenu";
import { SurfaceNav } from "./SurfaceNav";
import { Wordmark } from "./Wordmark";
import styles from "./AppShell.module.css";

// One top bar at every width, as on the reference sheet: the wordmark, then
// the five surfaces in tracked capitals. Below 60rem the links move into a
// menu sheet behind a single button. Exactly one of the two is visible.
//
// On the landing page the bar is held empty: entering Serene flies the
// bloom's flower into the logo's place, then the bar fills in.
export function AppShell({ children }: { children: ReactNode }) {
  const landing = usePathname() === "/";

  return (
    <div className={styles.shell}>
      <a href="#content" className={styles.skip}>
        Skip to content
      </a>

      <header className={styles.topbar} data-shell-bar="" data-landing={landing || undefined}>
        <Wordmark />
        <div className={styles.barNav}>
          <SurfaceNav variant="bar" />
        </div>
        <div className={styles.menu}>
          <MobileMenu />
        </div>
      </header>

      <main id="content" tabIndex={-1} className={styles.main} data-landing={landing || undefined}>
        {children}
      </main>
    </div>
  );
}
