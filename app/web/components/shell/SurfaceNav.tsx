"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LineMark } from "@/components/notation/LineMark";
import { SURFACES, isActive } from "@/lib/surfaces";
import styles from "./SurfaceNav.module.css";

type SurfaceNavProps = {
  /** rail: desktop sidebar. bar: tablet top bar. sheet: mobile menu. */
  variant: "rail" | "bar" | "sheet";
  label: string;
  onNavigate?: () => void;
};

export function SurfaceNav({ variant, label, onNavigate }: SurfaceNavProps) {
  const pathname = usePathname();
  const horizontal = variant === "bar";

  return (
    <nav aria-label={label} className={`${styles.nav} ${styles[variant]}`}>
      <ul className={styles.list}>
        {SURFACES.map((surface) => {
          const current = isActive(pathname, surface.href);
          return (
            <li key={surface.href}>
              <Link
                href={surface.href}
                className={styles.link}
                aria-current={current ? "page" : undefined}
                onClick={onNavigate}
              >
                <span className={styles.marker}>
                  <LineMark
                    certainty="unknown"
                    orientation={horizontal ? "horizontal" : "vertical"}
                  />
                </span>
                <span className={styles.text}>
                  <span className={styles.label}>{surface.label}</span>
                  {variant === "sheet" ? (
                    <span className={styles.summary}>{surface.summary}</span>
                  ) : null}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
