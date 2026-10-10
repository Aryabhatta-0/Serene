import { useId } from "react";
import { LineMark, type Certainty } from "./LineMark";
import styles from "./LineKey.module.css";

export type LineKeyEntry = {
  certainty: Certainty;
  term: string;
  description: string;
};

type LineKeyProps = {
  title: string;
  entries: readonly LineKeyEntry[];
};

// A legend for the certainty notation. It explains how to read Serene;
// it does not describe any particular family.
export function LineKey({ title, entries }: LineKeyProps) {
  const headingId = useId();
  return (
    <section className={styles.key} aria-labelledby={headingId}>
      <h2 id={headingId} className={styles.title}>
        {title}
      </h2>
      <dl className={styles.list}>
        {entries.map((entry) => (
          <div key={entry.certainty} className={styles.row}>
            <dt className={styles.term}>
              <LineMark certainty={entry.certainty} />
              {entry.term}
            </dt>
            <dd className={styles.description}>{entry.description}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
