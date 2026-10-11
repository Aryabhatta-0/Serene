import styles from "./LineMark.module.css";

// How firmly something is known, drawn as line style. The kinds mirror the
// Causal Twin edge categories (lib/causal-twin/categories.ts); this component
// only draws the notation and never implies that any such belief exists.
export type Certainty = "unknown" | "observed" | "tested" | "refuted" | "superseded";

type LineMarkProps = {
  certainty: Certainty;
  orientation?: "horizontal" | "vertical";
  className?: string;
};

export function LineMark({
  certainty,
  orientation = "horizontal",
  className,
}: LineMarkProps) {
  const vertical = orientation === "vertical";
  const end = vertical
    ? { x1: "50%", y1: "2", x2: "50%", y2: "100%" }
    : { x1: "2", y1: "50%", x2: "100%", y2: "50%" };

  return (
    <svg
      className={[styles.mark, styles[orientation], className]
        .filter(Boolean)
        .join(" ")}
      data-certainty={certainty}
      aria-hidden="true"
      focusable="false"
    >
      <line className={styles.stroke} {...end} />
      {certainty === "refuted" ? (
        <line className={styles.strike} {...end} />
      ) : null}
      {certainty === "superseded" ? (
        <line className={styles.hollow} {...end} />
      ) : null}
    </svg>
  );
}
