import type { ReactNode } from "react";
import { KIND_LABELS as ENTITY_LABELS, entityKind, formatDate } from "@/lib/causal-twin/provenance";
import { Reasons as RecordedReasons } from "@/components/system/Record";
import { explainReason } from "@/lib/memory/present";
import styles from "./Memory.module.css";

// Small pieces shared by the Memory surface. Every recorded item is named in
// words and shown with its id; every reason is explained and keeps its code.

export function Time({ iso }: { iso: string }) {
  return <time dateTime={iso}>{formatDate(iso)}</time>;
}

/** One recorded item: what it is, in words, and its id. Optionally a link to where it is explained. */
export function Entry({ id, href, note }: { id: string; href?: string; note?: string }) {
  const label = ENTITY_LABELS[entityKind(id)];
  const body = (
    <>
      <span className={styles.refLabel}>{label}</span>
      <code className={styles.refId}>{id}</code>
    </>
  );
  return (
    <span className={styles.ref} data-entity-id={id}>
      {href ? (
        <a href={href} className={styles.refLink}>
          {body}
        </a>
      ) : (
        body
      )}
      {note ? <span className={styles.refNote}>{note}</span> : null}
    </span>
  );
}

export function Entries({
  ids,
  empty,
  hrefOf,
  label,
}: {
  ids: readonly string[];
  empty: string;
  hrefOf?: (id: string) => string | undefined;
  label?: string;
}) {
  if (ids.length === 0) return <p className={styles.empty}>{empty}</p>;
  return (
    <ul className={styles.items} aria-label={label}>
      {ids.map((id) => (
        <li key={id}>
          <Entry id={id} href={hrefOf?.(id)} />
        </li>
      ))}
    </ul>
  );
}

/** Recorded reasons, each in plain words with its code. */
export function Reasons({ codes, label, tone }: { codes: readonly string[]; label: string; tone?: "plain" | "against" }) {
  return <RecordedReasons codes={codes} label={label} explain={explainReason} tone={tone} />;
}

export function Pairs({ children }: { children: ReactNode }) {
  return <dl className={styles.pairs}>{children}</dl>;
}

export function Pair({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}
