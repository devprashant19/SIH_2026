export type Side = "top" | "bottom" | "left" | "right";

export interface Placement {
  top: number;
  left: number;
  side: Side;
  /** Distance along the popover's edge at which the arrow should sit. */
  arrow: number;
}

export interface Rect {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

const ORDER: readonly Side[] = ["bottom", "top", "right", "left"];

/**
 * Where to put the popover relative to its target: flip to the first preferred side that fits,
 * clamp inside the viewport, and keep the arrow pointing at the target's centre even after the
 * clamp moves the box. Pure arithmetic, so it is unit-testable without a browser.
 */
export function place(
  target: Rect,
  pop: { w: number; h: number },
  viewport: { w: number; h: number },
  prefer: readonly Side[] = ORDER,
  gap = 10,
  edge = 12,
): Placement {
  const room: Record<Side, number> = {
    bottom: viewport.h - target.bottom - gap,
    top: target.top - gap,
    right: viewport.w - target.right - gap,
    left: target.left - gap,
  };
  const need = (s: Side) => (s === "top" || s === "bottom" ? pop.h : pop.w);

  const side =
    prefer.find((s) => room[s] >= need(s)) ??
    [...ORDER].sort((a, b) => room[b] - need(b) - (room[a] - need(a)))[0];

  let top: number;
  let left: number;
  if (side === "bottom" || side === "top") {
    top = side === "bottom" ? target.bottom + gap : target.top - gap - pop.h;
    left = target.left + target.width / 2 - pop.w / 2;
  } else {
    left = side === "right" ? target.right + gap : target.left - gap - pop.w;
    top = target.top + target.height / 2 - pop.h / 2;
  }

  left = Math.min(Math.max(left, edge), Math.max(edge, viewport.w - pop.w - edge));
  top = Math.min(Math.max(top, edge), Math.max(edge, viewport.h - pop.h - edge));

  const along = side === "top" || side === "bottom";
  const centre = along ? target.left + target.width / 2 - left : target.top + target.height / 2 - top;
  const span = along ? pop.w : pop.h;
  const arrow = Math.min(Math.max(centre, 14), Math.max(14, span - 14));

  return { top, left, side, arrow };
}
