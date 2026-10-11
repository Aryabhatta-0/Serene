"use client";

import { useEffect } from "react";

// The main flower's last petal settles at about 3.6s; release the page just
// after.
const BLOOM_MS = 3800;

// Runs in <head> before first paint, so the page never flashes fully drawn
// and then restarts. The bloom is the landing page's alone: it plays on every
// fresh load of "/", and never on a surface. Without scripts nothing is
// marked and the flowers are simply open.
export const BLOOM_SCRIPT = `if(location.pathname==="/")document.documentElement.dataset.bloom="play"`;

// Ends the intro: on schedule, or at once when the visitor presses, types or
// scrolls, so nobody has to wait through it.
export function BloomDirector() {
  useEffect(() => {
    const root = document.documentElement;
    if (root.dataset.bloom !== "play") return;

    const events = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
    const release = () => {
      window.clearTimeout(timer);
      for (const name of events) window.removeEventListener(name, finish);
    };
    const finish = () => {
      delete root.dataset.bloom;
      release();
    };
    const timer = window.setTimeout(finish, BLOOM_MS);
    for (const name of events) window.addEventListener(name, finish, { passive: true });
    // Unmounting only stops listening; it must not cut the intro short.
    return release;
  }, []);

  return null;
}
