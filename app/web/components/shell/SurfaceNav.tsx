"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/system/Icon";
import { SURFACES, isActive } from "@/lib/surfaces";
import styles from "./SurfaceNav.module.css";

type SurfaceNavProps = {
  /** bar: the top bar. sheet: the menu sheet on narrower screens. */
  variant: "bar" | "sheet";
  onNavigate?: () => void;
};

const ICONS: Record<string, IconName> = {
  "/today": "ring",
  "/memory": "memory",
  "/investigations": "branch",
  "/experiments": "flask",
  "/causal-twin": "twin",
};

export function SurfaceNav({ variant, onNavigate }: SurfaceNavProps) {
  const pathname = usePathname();

  return (
    <nav aria-label="Surfaces" className={styles[variant]}>
      <ul className={styles.list}>
        {SURFACES.map((surface, i) => (
          <li key={surface.href} style={{ "--n": i } as CSSProperties}>
            <Link
              href={surface.href}
              className={styles.link}
              aria-current={isActive(pathname, surface.href) ? "page" : undefined}
              onClick={onNavigate}
            >
              {variant === "sheet" ? <Icon name={ICONS[surface.href]} className={styles.icon} /> : null}
              <span className={styles.label}>{surface.label}</span>
              {variant === "sheet" ? (
                <span className={styles.summary}>{surface.question}</span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
