"use client";

import { useId, useState, type ReactNode, type Ref } from "react";
import { LineMark } from "@/components/notation/LineMark";
import { CATEGORIES, categorize } from "@/lib/causal-twin/categories";
import {
  KIND_LABELS,
  ROLE_LABELS,
  entityKind,
  formatDate,
  type EvidenceItem,
  type LinkRef,
} from "@/lib/causal-twin/provenance";
import styles from "./EdgeProvenance.module.css";

// Building blocks shared by both readings of the provenance panel (#39): the
// twin-only one and the full projection (#75).

// Long lists show this many items until the parent asks for the rest; the
// count of what is hidden is always stated.
const SHOWN = 6;

export function Section({
  title,
  name,
  headingRef,
  children,
}: {
  title: string;
  name: string;
  headingRef?: Ref<HTMLHeadingElement>;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section id={`provenance-${name}`} className={styles.section} aria-labelledby={id} data-section={name}>
      <h4 id={id} ref={headingRef} tabIndex={headingRef ? -1 : undefined} className={styles.heading}>
        {title}
      </h4>
      {children}
    </section>
  );
}

export function Evidence({ items, empty }: { items: EvidenceItem[]; empty: string }) {
  if (items.length === 0) return <p className={styles.empty}>{empty}</p>;
  return (
    <List
      items={items}
      keyOf={(item) => item.id}
      render={(item) => <Entry id={item.id} label={ROLE_LABELS[item.role]} role={item.role} />}
    />
  );
}

export function Ids({ ids, label, empty }: { ids: readonly string[]; label: string; empty: string }) {
  if (ids.length === 0) return <p className={styles.empty}>{empty}</p>;
  return <List items={ids} keyOf={(id) => id} render={(id) => <Entry id={id} label={label} />} />;
}

export function Notes({ title, notes, empty }: { title: string; notes: readonly string[]; empty: string }) {
  return (
    <>
      <h5 className={styles.subhead}>{title}</h5>
      {notes.length === 0 ? (
        <p className={styles.empty}>{empty}</p>
      ) : (
        <ul className={styles.notes}>
          {notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
    </>
  );
}

export function List<T>({
  items,
  render,
  keyOf,
}: {
  items: readonly T[];
  render: (item: T) => ReactNode;
  keyOf: (item: T) => string;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const shown = open ? items : items.slice(0, SHOWN);
  return (
    <>
      <ul id={listId} className={styles.items}>
        {shown.map((item) => (
          <li key={keyOf(item)}>{render(item)}</li>
        ))}
      </ul>
      {items.length > SHOWN ? (
        <button
          type="button"
          className={styles.more}
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(!open)}
        >
          {open ? "Show fewer" : `Show all ${items.length}`}
        </button>
      ) : null}
    </>
  );
}

/** One recorded item: what it is, in words, and its id. */
export function Entry({ id, label, note, role }: { id: string; label: string; note?: string; role?: string }) {
  return (
    <span className={styles.ref} data-entity-id={id} data-role={role}>
      <span className={styles.refLabel}>{label}</span>
      <code className={styles.refId}>{id}</code>
      {note ? <span className={styles.refNote}>{note}</span> : null}
    </span>
  );
}

/** An id that may be another link: chosen in place if it is on this map, otherwise just named. */
export function Link({ target, onGo }: { target: LinkRef; onGo: (edgeId: string) => void }) {
  if (!target.edge) {
    const kind = entityKind(target.id);
    return (
      <Entry id={target.id} label={KIND_LABELS[kind]} note={kind === "hypothesis" ? "Not on this map" : undefined} />
    );
  }
  const meta = CATEGORIES[categorize(target.edge)];
  return (
    <button
      type="button"
      className={styles.link}
      data-edge-ref={target.id}
      data-category={categorize(target.edge)}
      onClick={() => onGo(target.id)}
    >
      <span className={styles.linkState}>
        <LineMark certainty={meta.certainty} className={styles.linkMark} />
        {meta.term}
      </span>
      <span className={styles.linkText}>{target.edge.relationship}</span>
      <code className={styles.refId}>{target.id}</code>
    </button>
  );
}

export function Time({ iso }: { iso: string }) {
  return <time dateTime={iso}>{formatDate(iso)}</time>;
}
