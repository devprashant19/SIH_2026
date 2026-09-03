import type { Rect } from "../usePlacement";

/**
 * Four panels around the target plus a non-interactive ring.
 *
 * Not a large box-shadow: that is not hit-testable, so the dimmed region would not block
 * clicks. Four real elements give correct hit-testing for free, leave the hole clickable for
 * interactive steps, and are covered by the reduced-motion clamp already in globals.css.
 *
 * Geometry is in viewport coordinates from getBoundingClientRect, so nested scrollers need no
 * offset arithmetic.
 */
export function GuideSpotlight({
  rect,
  padding = 6,
  animate = true,
  onClickOutside,
}: {
  rect: Rect | null;
  padding?: number;
  animate?: boolean;
  onClickOutside?: () => void;
}) {
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;

  if (!rect) {
    // No anchor: dim the whole viewport so the popover still reads as modal.
    return <div className="fixed inset-0 z-guide-scrim bg-black/45" onClick={onClickOutside} />;
  }

  const t = Math.max(0, rect.top - padding);
  const l = Math.max(0, rect.left - padding);
  const r = Math.min(vw, rect.right + padding);
  const b = Math.min(vh, rect.bottom + padding);
  const transition = animate ? "transition-[top,left,width,height] duration-150" : "";
  const panel = `fixed z-guide-scrim bg-black/45 ${transition}`;

  return (
    <>
      <div className={panel} style={{ left: 0, top: 0, width: vw, height: t }} onClick={onClickOutside} />
      <div className={panel} style={{ left: 0, top: b, width: vw, height: Math.max(0, vh - b) }} onClick={onClickOutside} />
      <div className={panel} style={{ left: 0, top: t, width: l, height: Math.max(0, b - t) }} onClick={onClickOutside} />
      <div className={panel} style={{ left: r, top: t, width: Math.max(0, vw - r), height: Math.max(0, b - t) }} onClick={onClickOutside} />
      <div
        aria-hidden
        className={`pointer-events-none fixed z-guide-ring rounded-sm outline outline-2 outline-accent ${transition}`}
        style={{ left: l, top: t, width: Math.max(0, r - l), height: Math.max(0, b - t) }}
      />
    </>
  );
}
