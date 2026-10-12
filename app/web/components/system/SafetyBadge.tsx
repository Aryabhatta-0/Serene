import type { SafetyClass } from "@/lib/experiments/model";
import { SAFETY_LABELS } from "@/lib/experiments/present";
import { Icon } from "./Icon";
import styles from "./system.module.css";

const ICON = { GREEN: "leaf", AMBER: "hourglass", RED: "blocked" } as const;

// The safety classification as the kernel recorded it: its own name (GREEN,
// AMBER, RED), its mark, and what it means. Hue is never the only carrier:
// the word and the mark say it too. GREEN is drawn as a small leaf, not a
// tick, because a low risk is not Serene saying yes.
export function SafetyBadge({
  safety,
  size = "md",
  labelled = false,
}: {
  safety: SafetyClass | null;
  size?: "sm" | "md";
  /** Write the risk out in full ("Risk: Low") and mark it as the card's safety label. */
  labelled?: boolean;
}) {
  const term = safety ? SAFETY_LABELS[safety].term : "not checked yet";
  return (
    <span className={styles.safety} data-safety-class={safety ?? "UNCLASSIFIED"} data-size={size}>
      {safety ? <Icon name={ICON[safety]} className={styles.safetyIcon} /> : null}
      {safety ? <span className={styles.safetyName}>{safety}</span> : null}
      <span className={safety ? styles.safetyTerm : undefined} data-safety-label={labelled ? "" : undefined}>
        {labelled ? `Risk: ${term}` : safety ? term : "Not checked yet"}
      </span>
    </span>
  );
}
