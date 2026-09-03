/**
 * A stack of dismissable overlay layers, so Escape closes the topmost one only.
 *
 * The Drawer primitive registers its own Escape handler on `document` in the bubble phase.
 * This registry listens in the CAPTURE phase, which runs before the event descends to the
 * target, so calling stopPropagation() here prevents the target phase and all bubbling: the
 * Drawer's listener never sees that keystroke. When the stack is empty the handler returns
 * immediately without stopping anything, so behaviour without the guide is unchanged.
 */

interface Layer {
  id: number;
  onEscape: () => void;
}

const stack: Layer[] = [];
let seq = 0;
let listening = false;

function ensureListener(): void {
  if (listening) return;
  listening = true;
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Escape" || stack.length === 0) return;
      e.stopPropagation();
      e.preventDefault();
      stack[stack.length - 1].onEscape();
    },
    true,
  );
}

export function pushLayer(onEscape: () => void): number {
  const id = ++seq;
  stack.push({ id, onEscape });
  ensureListener();
  return id;
}

export function popLayer(id: number): void {
  const i = stack.findIndex((l) => l.id === id);
  if (i >= 0) stack.splice(i, 1);
}

export function isTopLayer(id: number): boolean {
  return stack.length > 0 && stack[stack.length - 1].id === id;
}

export function layerDepth(): number {
  return stack.length;
}

/** Test-only: drop every registered layer. */
export function resetLayers(): void {
  stack.length = 0;
}
