import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom lacks the layout APIs React Flow measures with. These stand-ins only
// let it mount; geometry is checked in the browser by the Playwright suite.
// Reports one wide canvas, as a desktop browser would on first layout.
class ResizeObserverStub {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe(target: Element) {
    this.callback(
      [{ target, contentRect: { width: 1100, height: 540 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}

class DOMMatrixReadOnlyStub {
  m22 = 1;
}

Object.assign(globalThis, {
  ResizeObserver: ResizeObserverStub,
  DOMMatrixReadOnly: DOMMatrixReadOnlyStub,
});

Object.defineProperties(HTMLElement.prototype, {
  offsetHeight: { get() { return parseFloat(this.style.height) || 1; } },
  offsetWidth: { get() { return parseFloat(this.style.width) || 1; } },
});

(SVGElement.prototype as unknown as { getBBox: () => DOMRect }).getBBox = () =>
  ({ x: 0, y: 0, width: 0, height: 0 }) as DOMRect;

// Wide screen, no reduced-motion preference.
window.matchMedia = ((query: string) => ({
  matches: query.includes("min-width"),
  media: query,
  onchange: null,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia;

afterEach(cleanup);
