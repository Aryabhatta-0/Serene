import type { ReactNode } from "react";
import styles from "./template.module.css";

// A template remounts on every navigation, so the arrival transition runs
// once per route change and never on re-renders within a surface.
export default function SurfaceTransition({ children }: { children: ReactNode }) {
  return <div className={styles.arrive}>{children}</div>;
}
