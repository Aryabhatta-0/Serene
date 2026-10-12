import type { ReactNode } from "react";
import styles from "./system.module.css";

// Serene's small icon set: drawn on a 16px grid in one 1.5px hairline stroke,
// to sit beside tracked labels. Icons are never the only carrier of meaning;
// each one stands next to its word.
const PATHS: Record<IconName, ReactNode> = {
  arrow: <path d="M3 8h10M9 4l4 4-4 4" />,
  // Reversible: a line that returns on itself.
  undo: <path d="M5.5 4 3 6.5 5.5 9M3 6.5h6.5a3.5 3.5 0 0 1 0 7H7" />,
  // How long: a dial.
  clock: (
    <>
      <circle cx="8" cy="8" r="5.75" />
      <path d="M8 4.75V8l2.25 1.5" />
    </>
  ),
  // What will be watched.
  eye: (
    <>
      <path d="M1.75 8S4 3.75 8 3.75 14.25 8 14.25 8 12 12.25 8 12.25 1.75 8 1.75 8Z" />
      <circle cx="8" cy="8" r="2" />
    </>
  ),
  // Effort: a small weight.
  weight: <path d="M5.5 5.5h5l2 7.5h-9l2-7.5ZM6.5 5.5a1.5 1.5 0 1 1 3 0" />,
  // GREEN: a leaf, small and alive. Not a tick: green is not "yes".
  leaf: (
    <>
      <path d="M3 13c0-6 4-9.5 10-10-.5 6-4 10-10 10Z" />
      <path d="M3 13c2.5-3 4.5-4.75 7-6.5" />
    </>
  ),
  // AMBER: an hourglass, time to deliberate.
  hourglass: <path d="M4 2.5h8M4 13.5h8M5 2.5c0 3 6 3.5 6 5.5s-6 2.5-6 5.5M11 2.5c0 3-6 3.5-6 5.5s6 2.5 6 5.5" />,
  // RED: a barred circle, closed.
  blocked: (
    <>
      <circle cx="8" cy="8" r="5.75" />
      <path d="m4 12 8-8" />
    </>
  ),
  // A question put to the parent.
  ask: (
    <>
      <path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2v-7Z" />
      <path d="M6.75 5.75a1.3 1.3 0 1 1 1.8 1.2c-.4.2-.55.45-.55.8" />
      <path d="M8 9.1v.05" />
    </>
  ),
  // Looking something up.
  search: (
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="m10.25 10.25 3.25 3.25" />
    </>
  ),
  // Checked and accepted.
  check: <path d="m3.5 8.5 3 3 6-7" />,
  // Failed its checks.
  cross: <path d="m4.5 4.5 7 7M11.5 4.5l-7 7" />,
  // A decision to be made by the parent.
  hand: <path d="M5.5 8V3.75a1 1 0 0 1 2 0V7.5m0-.5V2.75a1 1 0 0 1 2 0V7.5m0-.25V4a1 1 0 0 1 2 0v5.25c0 2.5-1.75 4.25-4.25 4.25-1.75 0-2.75-.75-3.75-2.25L2.5 8.6a1 1 0 0 1 1.6-1.15L5.5 9" />,
  // Memory: a pressed leaf in a page.
  memory: (
    <>
      <path d="M3.5 2.5h7l2 2v9h-9v-11Z" />
      <path d="M6 11c0-2.5 1.5-4.25 4-4.5-.25 2.5-1.75 4.5-4 4.5Zm0 0 2-2" />
    </>
  ),
  // Experiments: a small vessel.
  flask: <path d="M6 2.5h4M6.75 2.5v4L3.25 12.5a.75.75 0 0 0 .65 1.1h8.2a.75.75 0 0 0 .65-1.1L9.25 6.5v-4M4.75 10h6.5" />,
  // Investigations: competing branches.
  branch: (
    <>
      <circle cx="4" cy="3.75" r="1.5" />
      <circle cx="4" cy="12.25" r="1.5" />
      <circle cx="12" cy="8" r="1.5" />
      <path d="M4 5.25v5.5M4 8h3.5a3 3 0 0 0 3-3V8" />
    </>
  ),
  // The Causal Twin: linked nodes.
  twin: (
    <>
      <circle cx="3.5" cy="4" r="1.75" />
      <circle cx="12.5" cy="4" r="1.75" />
      <circle cx="8" cy="12" r="1.75" />
      <path d="M5.25 4h5.5M4.4 5.55l2.75 4.9M11.6 5.55l-2.75 4.9" />
    </>
  ),
  // Live / in sync: a ring.
  ring: <circle cx="8" cy="8" r="5.75" />,
};

export type IconName =
  | "arrow"
  | "undo"
  | "clock"
  | "eye"
  | "weight"
  | "leaf"
  | "hourglass"
  | "blocked"
  | "ask"
  | "search"
  | "check"
  | "cross"
  | "hand"
  | "memory"
  | "flask"
  | "branch"
  | "twin"
  | "ring";

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      className={[styles.icon, className].filter(Boolean).join(" ")}
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
