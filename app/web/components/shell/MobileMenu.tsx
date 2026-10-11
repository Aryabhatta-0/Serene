"use client";

import { useEffect, useRef, useState } from "react";
import { SurfaceNav } from "./SurfaceNav";
import { Wordmark } from "./Wordmark";
import styles from "./MobileMenu.module.css";

export function MobileMenu() {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const pressedBackdrop = useRef(false);
  const [open, setOpen] = useState(false);

  const close = () => dialogRef.current?.close();

  // When the layout hides this menu (the inline nav has taken over), close
  // the sheet so an invisible modal can never trap the page. Watching the
  // trigger keeps the breakpoint in CSS alone.
  useEffect(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width === 0) dialogRef.current?.close();
    });
    observer.observe(trigger);
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <button
        ref={triggerRef}
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
        <svg viewBox="0 0 24 14" aria-hidden="true" focusable="false">
          <line x1="1" y1="1" x2="23" y2="1" />
          <line x1="1" y1="7" x2="23" y2="7" />
          <line x1="1" y1="13" x2="23" y2="13" />
        </svg>
        <span className="visually-hidden">Surfaces</span>
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
            <button type="button" className={`button ${styles.close}`} onClick={close}>
              Close
            </button>
          </div>
          <SurfaceNav variant="sheet" onNavigate={close} />
        </div>
      </dialog>
    </>
  );
}
