"use client";

import { useEffect, useRef, useState } from "react";
import { SurfaceNav } from "./SurfaceNav";
import { Wordmark } from "./Wordmark";
import styles from "./MobileMenu.module.css";

// Must match the 45rem breakpoint in AppShell.module.css, where the inline
// top-bar nav takes over from this menu.
const INLINE_NAV_QUERY = "(min-width: 45rem)";

export function MobileMenu() {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const pressedBackdrop = useRef(false);
  const [open, setOpen] = useState(false);

  const close = () => dialogRef.current?.close();

  useEffect(() => {
    const query = window.matchMedia(INLINE_NAV_QUERY);
    const onChange = () => {
      if (query.matches) dialogRef.current?.close();
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return (
    <>
      <button
        type="button"
        className={styles.trigger}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="surface-menu"
        onClick={() => {
          dialogRef.current?.showModal();
          setOpen(true);
        }}
      >
        <svg viewBox="0 0 20 14" aria-hidden="true" focusable="false">
          <line x1="1" y1="2" x2="19" y2="2" />
          <line x1="1" y1="7" x2="19" y2="7" />
          <line x1="1" y1="12" x2="19" y2="12" />
        </svg>
        Surfaces
      </button>

      <dialog
        id="surface-menu"
        ref={dialogRef}
        className={styles.sheet}
        aria-label="Serene surfaces"
        onClose={() => setOpen(false)}
        // A press on the backdrop lands on the dialog element itself. Require
        // it to start there too, so a drag out of the panel does not close it.
        onPointerDown={(event) => {
          pressedBackdrop.current = event.target === event.currentTarget;
        }}
        onClick={(event) => {
          if (pressedBackdrop.current && event.target === event.currentTarget) close();
          pressedBackdrop.current = false;
        }}
      >
        <div className={styles.panel}>
          <div className={styles.header}>
            <Wordmark onNavigate={close} />
            <button type="button" className={styles.close} onClick={close}>
              Close
            </button>
          </div>
          <SurfaceNav variant="sheet" label="Surfaces" onNavigate={close} />
        </div>
      </dialog>
    </>
  );
}
