import type { Rect } from "../usePlacement";

/**
 * Four blurred, dimmed panels around the target plus a glowing ring on it.
 *
 * Not a large box-shadow: a shadow is not hit-testable, so the dimmed region would not block
 * clicks. Four real elements give correct hit-testing for free and leave the hole itself
 * untouched, so the highlighted control stays sharp, readable and clickable while everything
 * else is inert. Geometry is in viewport coordinates from getBoundingClientRect, so nested
 * scrollers need no offset arithmetic.
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
  const veil = "fixed bg-black/40 backdrop-blur-[3px]";
  const transition = animate ? " transition-[top,left,width,height] duration-300 ease-out" : "";

  if (!rect) {
    // No target: veil the whole viewport so the popover still reads as modal.
    return <div className={`${veil} inset-0 z-guide-scrim`} onClick={onClickOutside} />;
  }

  const t = Math.max(0, rect.top - padding);
  const l = Math.max(0, rect.left - padding);
  const r = Math.min(vw, rect.right + padding);
  const b = Math.min(vh, rect.bottom + padding);
  const panel = `${veil} z-guide-scrim${transition}`;

  return (
    <>
      <div className={panel} style={{ left: 0, top: 0, width: vw, height: t }} onClick={onClickOutside} />
      <div className={panel} style={{ left: 0, top: b, width: vw, height: Math.max(0, vh - b) }} onClick={onClickOutside} />
      <div className={panel} style={{ left: 0, top: t, width: l, height: Math.max(0, b - t) }} onClick={onClickOutside} />
      <div className={panel} style={{ left: r, top: t, width: Math.max(0, vw - r), height: Math.max(0, b - t) }} onClick={onClickOutside} />
      <div
        aria-hidden
        className={`pointer-events-none fixed z-guide-ring rounded-md ring-2 ring-accent${transition}`}
        style={{
          left: l,
          top: t,
          width: Math.max(0, r - l),
          height: Math.max(0, b - t),
          // A soft outward glow so the cutout reads as lit rather than merely un-dimmed.
          boxShadow: "0 0 0 4px var(--color-accent-bg), 0 0 18px 2px rgb(47 91 234 / 0.35)",
        }}
      />
    </>
  );
}
