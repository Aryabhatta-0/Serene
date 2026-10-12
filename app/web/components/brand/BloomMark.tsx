import { Hellebore } from "./Hellebore";
import styles from "./BloomMark.module.css";

// The Serene logo: the bloom's hellebore, seen from above, on no ground of
// its own. The favicon and home-screen icons are exported from this element
// (scripts/export-brand.mjs). On entering from the landing page the bloom's
// main flower flies into its place (components/landing/Landing.tsx).
export function BloomMark({ className }: { className?: string }) {
  return (
    <span className={[styles.mark, className].filter(Boolean).join(" ")} aria-hidden="true" data-brand-mark="">
      <Hellebore className={styles.flower} name="mark" />
    </span>
  );
}
