import type { ReactNode } from "react";
import type { EpistemicLevel } from "@/lib/causal-twin/model";
import { LEVEL_NAMES } from "@/lib/causal-twin/provenance";
import styles from "./system.module.css";

const RUNGS: readonly EpistemicLevel[] = [0, 1, 2, 3, 4, 5];

// The epistemic ladder, drawn: six rungs from raw evidence to a contextual
// learning, the rungs climbed solid, the rest dotted. It is the kernel's
// recorded level, never a score, and the words always stand beside it.
export function LevelLadder({
  level,
  children,
  className,
}: {
  level: EpistemicLevel | null;
  /** The level in words; defaults to "Level n of 5: Name". */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <span className={[styles.ladder, className].filter(Boolean).join(" ")} data-level={level ?? "none"}>
      <span className={styles.rungs} aria-hidden="true">
        {RUNGS.map((rung) => (
          <span
            key={rung}
            className={styles.rung}
            data-climbed={level !== null && rung <= level ? "" : undefined}
            data-at={rung === level ? "" : undefined}
          />
        ))}
      </span>
      <span className={styles.ladderText}>
        {children ?? (level === null ? "No evidence level" : `Level ${level} of 5: ${LEVEL_NAMES[level]}`)}
      </span>
    </span>
  );
}
