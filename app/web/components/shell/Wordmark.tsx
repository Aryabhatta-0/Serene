import Link from "next/link";
import { BloomMark } from "@/components/brand/BloomMark";
import styles from "./Wordmark.module.css";

// The Serene mark: the bloom, beside the name in tracked capitals.
export function Wordmark({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link href="/today" className={styles.wordmark} onClick={onNavigate}>
      <BloomMark />
      <span className={styles.name}>Serene</span>
    </Link>
  );
}
