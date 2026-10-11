import type { CSSProperties } from "react";
import styles from "./Hellebore.module.css";

// One hellebore: five photographic petals around a cluster of stamens. Each
// petal pivots at its base, so when the landing page loads the flower opens
// from a closed cup rather than fading in (see Hellebore.module.css). The same
// flower is the landing bloom, the logo and the favicon.
//
// The parent sizes it with --petal-w, --petal-h and --centre, and may set
// --bloom-delay and --bloom-dur to time its opening. `name` marks a flower the
// landing transition needs to find (the bloom's main flower, the logo's).

export const PETAL_SRC = "/brand/bloom/petal.webp";

// Where each petal settles (clockwise from the top) and how wide it spreads.
const PETALS = [
  { angle: -7, spread: 1 },
  { angle: 66, spread: 0.97 },
  { angle: 139, spread: 0.94 },
  { angle: -149, spread: 1.02 },
  { angle: -77, spread: 0.96 },
] as const;

// Stamens on a golden-angle spiral, computed once so server and client agree.
const STAMENS = Array.from({ length: 42 }, (_, i) => {
  const theta = i * 2.399963;
  const radius = Math.sqrt(i / 42) * 18;
  const x = (24 + Math.cos(theta) * radius).toFixed(2);
  const y = (24 + Math.sin(theta) * radius).toFixed(2);
  return { x, y, turn: ((i * 137.5) % 360).toFixed(1), pale: i % 3 !== 0 };
});

type HelleboreProps = { className?: string; style?: CSSProperties; name?: string };

export function Hellebore({ className, style, name }: HelleboreProps) {
  return (
    <div
      className={[styles.flower, className].filter(Boolean).join(" ")}
      style={style}
      data-flower={name}
    >
      {PETALS.map((petal, i) => (
        <div
          key={petal.angle}
          className={styles.arm}
          style={
            {
              "--angle": `${petal.angle}deg`,
              // Closed, the petals cup together pointing up.
              "--folded": `${(i - 2) * 9 - 8}deg`,
              "--spread": petal.spread,
              "--i": i,
            } as CSSProperties
          }
        >
          <img
            className={styles.petal}
            src={PETAL_SRC}
            alt=""
            width={600}
            height={641}
            decoding="async"
            draggable={false}
          />
        </div>
      ))}
      <svg className={styles.centre} viewBox="0 0 48 48" focusable="false">
        <circle cx="24" cy="24" r="11" fill="#6d7a42" />
        {STAMENS.map((s) => (
          <g key={`${s.x} ${s.y}`}>
            <path d={`M24 24L${s.x} ${s.y}`} stroke="#a7ac62" strokeWidth={0.7} />
            <ellipse
              cx={s.x}
              cy={s.y}
              rx={1.3}
              ry={1.9}
              fill={s.pale ? "#d9d7a0" : "#bec48a"}
              transform={`rotate(${s.turn} ${s.x} ${s.y})`}
            />
          </g>
        ))}
        <circle cx="24" cy="24" r="4" fill="#82914e" />
      </svg>
    </div>
  );
}
