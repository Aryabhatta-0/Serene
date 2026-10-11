import { Hellebore } from "./Hellebore";
import styles from "./BloomArt.module.css";

// The Serene bloom: two photographic hellebores and a closed bud on long
// stems, behind two panes of frosted glass. It is laid out on a square scene
// in percentages and container units, so the parent only sets its size.
// Decorative throughout: hidden from assistive technology.
//
// Stems are in the scene's 1000-unit space and run past its foot; the parent
// clips them where the plate ends.

const STEMS = [
  // To the back flower, the main flower and the bud.
  { d: "M509 1400L509 1030C508 829 464 581 440 365", width: 10, light: "M505 1400L505 1010C504 799 461 570 437 378" },
  { d: "M587 1400L587 1030C594 804 619 580 641 418", width: 9, light: "M584 1400L584 1010C591 804 616 580 638 430" },
  { d: "M431 1400L431 1030C426 875 396 712 344 679", width: 7, light: "M427 1400L427 1010C423 875 393 712 341 684" },
] as const;

export function BloomArt({ id, className }: { id: string; className?: string }) {
  return (
    <div className={[styles.frame, className].filter(Boolean).join(" ")} aria-hidden="true">
      <div className={styles.scene} data-bloom-art="">
        <svg className={styles.stems} viewBox="0 0 1000 1400" fill="none" focusable="false">
          <defs>
            <linearGradient id={`${id}-stem`} x1="0" y1="0" x2="1" y2="0">
              <stop stopColor="#88966b" />
              <stop offset="0.35" stopColor="#a9b783" />
              <stop offset="0.6" stopColor="#737e48" />
              <stop offset="1" stopColor="#aebd8e" />
            </linearGradient>
            <filter id={`${id}-grain`}>
              <feTurbulence type="fractalNoise" baseFrequency="0.15 0.65" numOctaves={3} seed={9} result="noise" />
              <feColorMatrix in="noise" type="saturate" values="0" result="mono" />
              <feComposite in="mono" in2="SourceGraphic" operator="in" result="texture" />
              <feBlend in="SourceGraphic" in2="texture" mode="soft-light" />
            </filter>
          </defs>
          <g filter={`url(#${id}-grain)`} stroke={`url(#${id}-stem)`} strokeLinecap="round">
            {STEMS.map((stem) => (
              <path key={stem.d} className={styles.stem} d={stem.d} strokeWidth={stem.width} pathLength={1} />
            ))}
          </g>
          <g stroke="#d2d9ae" strokeOpacity={0.5} strokeWidth={1.5}>
            {STEMS.map((stem) => (
              <path key={stem.light} className={styles.stem} d={stem.light} pathLength={1} />
            ))}
          </g>
        </svg>

        <Hellebore className={styles.back} />
        <Hellebore className={styles.main} name="main" />
        <img
          className={styles.bud}
          src="/brand/bloom/bud.webp"
          alt=""
          width={420}
          height={615}
          decoding="async"
          draggable={false}
        />

        <span className={`${styles.glass} ${styles.paneFront}`} />
        <span className={`${styles.glass} ${styles.paneBack}`} />
      </div>
    </div>
  );
}
