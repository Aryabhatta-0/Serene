"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BloomArt } from "@/components/brand/BloomArt";
import styles from "./Landing.module.css";

const DESTINATION = "/today";

// The glass, stems, bud and words fade first, so the flower leaves from
// under clear air rather than popping out from behind frosted glass.
const FADE_MS = 320;
const FLIGHT_MS = 1000;
// Long enough for the bar's staggered entrance (AppShell, Wordmark,
// SurfaceNav) to finish after the flower lands.
const REVEAL_MS = 1200;

// Flies the bloom's main flower into the logo's tile. A copy of the flower
// travels on a fixed layer above the page: horizontal and vertical motion
// take different curves, so it rises and swings across in an arc, shrinking
// and turning to the logo flower's size and angle on the way.
function flyToMark(flower: HTMLElement, target: HTMLElement): Promise<void> {
  const from = flower.getBoundingClientRect();
  const to = target.getBoundingClientRect();
  const petal = flower.querySelector("img");
  const targetPetal = target.querySelector("img");
  if (!petal || !targetPetal) return Promise.resolve();

  // The copy keeps the flower's classes; only its size, set in container
  // units on the plate, has to be fixed in pixels off the plate.
  const copy = flower.cloneNode(true) as HTMLElement;
  copy.style.setProperty("--petal-w", `${petal.offsetWidth}px`);
  copy.style.setProperty("--petal-h", `${petal.offsetHeight}px`);
  copy.style.setProperty("--centre", `${flower.querySelector("svg")?.clientWidth ?? 0}px`);

  const across = document.createElement("div");
  const up = document.createElement("div");
  across.className = styles.flight;
  up.append(copy);
  across.append(up);
  document.body.append(across);
  flower.style.visibility = "hidden";

  const scale = targetPetal.offsetHeight / petal.offsetHeight;
  // The bloom's flower is drawn at 16deg, the logo's at 4deg.
  const turn = -12;

  const timing = { duration: FLIGHT_MS, fill: "forwards" } as const;
  across.animate(
    [{ transform: `translateX(${from.x}px)` }, { transform: `translateX(${to.x}px)` }],
    { ...timing, easing: "cubic-bezier(0.65, 0, 0.35, 1)" },
  );
  const flight = up.animate(
    [
      { transform: `translateY(${from.y}px)` },
      { transform: `translateY(${to.y}px) rotate(${turn}deg) scale(${scale})` },
    ],
    { ...timing, easing: "cubic-bezier(0.3, 0, 0.15, 1)" },
  );
  copy.animate([{ filter: getComputedStyle(flower).filter }, { filter: "none" }], timing);

  return flight.finished.then(
    () => {
      // Hand over to the real logo on the next frame, once it is showing.
      requestAnimationFrame(() => across.remove());
    },
    () => across.remove(),
  );
}

export function Landing() {
  const router = useRouter();
  const leaving = useRef(false);
  const [state, setState] = useState<"rest" | "leaving">("rest");
  const heroRef = useRef<HTMLElement>(null);

  useEffect(() => {
    router.prefetch(DESTINATION);
  }, [router]);

  // The bar's entrance outlives this page: clear the flag once it is done.
  useEffect(() => {
    const root = document.documentElement;
    return () => {
      window.setTimeout(() => delete root.dataset.enter, REVEAL_MS);
    };
  }, []);

  const enter = async () => {
    if (leaving.current) return;
    leaving.current = true;

    const root = document.documentElement;
    // Entering ends the intro at once, with every flower fully open.
    delete root.dataset.bloom;
    setState("leaving");

    const flower = heroRef.current?.querySelector<HTMLElement>('[data-flower="main"]');
    const target = document.querySelector<HTMLElement>('[data-shell-bar] [data-flower="mark"]');
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    await new Promise((resolve) => window.setTimeout(resolve, FADE_MS));
    if (flower && target && !still) await flyToMark(flower, target);

    root.dataset.enter = "";
    // The button is about to go; keep keyboard focus at the start of the bar
    // that has just filled in, rather than losing it to the page.
    document.querySelector<HTMLElement>("[data-shell-bar] a")?.focus({ preventScroll: true });
    router.push(DESTINATION);
  };

  return (
    <header ref={heroRef} className={styles.hero} data-state={state}>
      <div className={styles.stage}>
        <BloomArt id="landing" className={styles.bloom} />
        <div className={styles.heading}>
          <p className={styles.kicker}>Family intelligence, kept honest</p>
          <h1 className={styles.title}>Serene</h1>
        </div>
      </div>
      <p className={styles.lead}>
        Understand what is happening with your child, and see why Serene
        believes what it believes.
      </p>
      <p className={styles.tagline}>
        What happened, what Serene remembers and what it believes are kept
        apart.
      </p>
      <button type="button" className={`button ${styles.enter}`} onClick={enter}>
        Enter Serene
        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path d="M3 8h10M9 4l4 4-4 4" />
        </svg>
      </button>
    </header>
  );
}
