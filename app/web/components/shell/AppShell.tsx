import type { ReactNode } from "react";
import { MobileMenu } from "./MobileMenu";
import { RecordStatus } from "./RecordStatus";
import { SurfaceNav } from "./SurfaceNav";
import { Wordmark } from "./Wordmark";
import styles from "./AppShell.module.css";

// Navigation adapts structurally rather than shrinking: a sidebar rail on
// desktop, an inline top bar on tablets, and a menu sheet on phones. Exactly
// one of the three is rendered visible at any width.
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <a href="#content" className={styles.skip}>
        Skip to content
      </a>

      <header className={styles.rail}>
        <Wordmark />
        <SurfaceNav variant="rail" label="Surfaces" />
        <div className={styles.railFooter}>
          <RecordStatus />
          <p className={styles.tagline}>
            What happened, what Serene remembers and what it believes are kept
            apart.
          </p>
        </div>
      </header>

      <header className={styles.topbar}>
        <Wordmark />
        <div className={styles.barNav}>
          <SurfaceNav variant="bar" label="Surfaces" />
        </div>
        <div className={styles.menu}>
          <MobileMenu />
        </div>
      </header>

      <main id="content" tabIndex={-1} className={styles.main}>
        {children}
      </main>
    </div>
  );
}
