import type { Anchor } from "./model";
import type { Rect } from "./usePlacement";

/**
 * The first VISIBLE element carrying this anchor, in document order. Visibility matters because
 * a few controls legitimately render more than once, for instance the period selector, which is
 * in the top bar and again on the ingestion screen.
 */
export function resolveAnchor(anchor: Anchor): HTMLElement | null {
  const escaped = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(anchor) : anchor.replace(/"/g, '\\"');
  const all = document.querySelectorAll<HTMLElement>(`[data-guide="${escaped}"]`);
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden") return el;
  }
  return null;
}

export function rectOf(el: Element): Rect {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
}

export function sameRect(a: Rect | null, b: Rect | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    Math.abs(a.top - b.top) < 0.5 &&
    Math.abs(a.left - b.left) < 0.5 &&
    Math.abs(a.width - b.width) < 0.5 &&
    Math.abs(a.height - b.height) < 0.5
  );
}

/**
 * Wait for an anchor to appear. Driven by a mutation observer rather than a fixed poll, because
 * the usual reason an anchor is missing is that a query boundary is still showing a skeleton.
 * Resolves with null once the budget runs out. `timeoutMs` of 0 means wait indefinitely.
 */
export function waitForAnchor(anchor: Anchor, timeoutMs = 1500): { promise: Promise<HTMLElement | null>; cancel: () => void } {
  let done = false;
  let observer: MutationObserver | null = null;
  let timer: number | null = null;

  const cleanup = () => {
    observer?.disconnect();
    observer = null;
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
  };

  const promise = new Promise<HTMLElement | null>((resolve) => {
    const finish = (el: HTMLElement | null) => {
      if (done) return;
      done = true;
      cleanup();
      resolve(el);
    };
    const found = resolveAnchor(anchor);
    if (found) return finish(found);
    observer = new MutationObserver(() => {
      const el = resolveAnchor(anchor);
      if (el) finish(el);
    });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-guide", "style", "class"] });
    if (timeoutMs > 0) timer = window.setTimeout(() => finish(resolveAnchor(anchor)), timeoutMs);
  });

  return {
    promise,
    cancel: () => {
      done = true;
      cleanup();
    },
  };
}
