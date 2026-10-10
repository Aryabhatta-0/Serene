import type { ReactNode } from "react";
import styles from "./Page.module.css";

type PageProps = {
  title: string;
  lead: string;
  children?: ReactNode;
};

// Every surface shares one reading column and header rhythm.
export function Page({ title, lead, children }: PageProps) {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.lead}>{lead}</p>
      </header>
      {children}
    </div>
  );
}
