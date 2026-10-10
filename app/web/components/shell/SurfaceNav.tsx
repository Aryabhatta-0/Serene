"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LineMark } from "@/components/notation/LineMark";
import { SURFACES, isActive } from "@/lib/surfaces";
import styles from "./SurfaceNav.module.css";

type SurfaceNavProps = {
  /** rail: desktop sidebar. bar: tablet top bar. sheet: phone menu. */
  variant: "rail" | "bar" | "sheet";
  onNavigate?: () => void;
};

export function SurfaceNav({ variant, onNavigate }: SurfaceNavProps) {
  const pathname = usePathname();

  return (
    <nav aria-label="Surfaces" className={styles[variant]}>
      <ul className={styles.list}>
        {SURFACES.map((surface) => (
          <li key={surface.href}>
            <Link
              href={surface.href}
              className={styles.link}
              aria-current={isActive(pathname, surface.href) ? "page" : undefined}
              onClick={onNavigate}
            >
              <span className={styles.marker}>
                <LineMark
                  certainty="unknown"
                  orientation={variant === "bar" ? "horizontal" : "vertical"}
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
        ))}
      </ul>
    </nav>
  );
}
