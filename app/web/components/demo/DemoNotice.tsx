import styles from "./DemoNotice.module.css";

export function DemoNotice() {
  return (
    <p role="note" className={styles.notice} data-demo-notice>
      Demo mode · This page uses fictional sample data. It is not a family record, and actions here
      do not reach Serene.
    </p>
  );
}
