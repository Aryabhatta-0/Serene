import type { ReactNode } from "react";
import { formatDate } from "@/lib/causal-twin/provenance";
import styles from "./system.module.css";

// Small pieces every surface uses to show what the kernel recorded: reasons
// (each explained in words, its code always kept), term/value pairs and dates.

export type Explained = { text: string; known: boolean };

/** Recorded reasons, each in plain words with its code. */
export function Reasons({
  codes,
  label,
  explain,
  tone = "plain",
}: {
  codes: readonly string[];
  label: string;
  explain: (code: string) => Explained;
  /** "against": reasons something was refused, blocked or rejected. */
  tone?: "plain" | "against";
}) {
  if (codes.length === 0) return null;
  return (
    <ul className={styles.reasons} aria-label={label} data-tone={tone}>
      {codes.map((code, i) => {
        const reason = explain(code);
        return (
          <li key={i} className={styles.reason} data-reason-code={code} data-known={reason.known}>
            <span className={styles.reasonText}>{reason.text}</span>
            <code className={styles.code}>{code}</code>
          </li>
        );
      })}
    </ul>
  );
}

export function Pairs({ children, layout = "rows" }: { children: ReactNode; layout?: "rows" | "grid" }) {
  return (
    <dl className={styles.pairs} data-layout={layout}>
      {children}
    </dl>
  );
}

export function Pair({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function Time({ iso }: { iso: string }) {
  return <time dateTime={iso}>{formatDate(iso)}</time>;
}

/** A link onward to another part of Serene, with its arrow. */
export function Onward({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="onward-link">
      {children}
      <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path d="M3 8h10M9 4l4 4-4 4" />
      </svg>
    </a>
  );
}
