import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { place, type Placement, type Rect, type Side } from "../usePlacement";

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/** Below this width the popover docks to the bottom of the screen instead of chasing the
 *  target, because a 360px card cannot be placed beside anything on a phone. */
const DOCK_BELOW = 640;

export interface GuidePopoverProps {
  rect: Rect | null;
  title: string;
  body: string;
  /** How the feature is built. Rendered under a quiet heading when present. */
  note?: string;
  /** Set when the target could not be found and the step chose to explain rather than skip. */
  missingNote?: string;
  index: number;
  total: number;
  prefer?: readonly Side[];
  animate?: boolean;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}

export function GuidePopover({
  rect,
  title,
  body,
  note,
  missingNote,
  index,
  total,
  prefer,
  animate = true,
  onNext,
  onBack,
  onSkip,
}: GuidePopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [docked, setDocked] = useState(() => window.innerWidth < DOCK_BELOW);
  const isLast = index + 1 === total;

  useEffect(() => {
    const onResize = () => setDocked(window.innerWidth < DOCK_BELOW);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Two-pass measurement: render hidden, measure, place, paint once.
  useLayoutEffect(() => {
    if (docked || !ref.current || !rect) {
      setPlacement(null);
      return;
    }
    const box = ref.current.getBoundingClientRect();
    setPlacement(
      place(
        rect,
        { w: box.width, h: box.height },
        { w: document.documentElement.clientWidth, h: document.documentElement.clientHeight },
        prefer,
      ),
    );
  }, [rect, prefer, title, body, note, docked]);

  useEffect(() => {
    ref.current?.focus();
  }, [index]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab" || !ref.current) return;
    const items = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === ref.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const centred = !docked && rect === null;
  const style: React.CSSProperties = docked
    ? { left: 12, right: 12, bottom: 12 }
    : centred
      ? { top: "50%", left: "50%", transform: "translate(-50%, -50%)" }
      : placement
        ? { top: placement.top, left: placement.left }
        : { top: 0, left: 0, visibility: "hidden" };

  return (
    <div
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-labelledby="guide-popover-title"
      aria-describedby="guide-popover-body"
      tabIndex={-1}
      onKeyDown={onKeyDown}
      style={{ ...style, maxHeight: "calc(100vh - 24px)" }}
      className={cn(
        "fixed z-guide-popover overflow-auto rounded-lg border border-border bg-bg p-4 shadow-drawer",
        docked ? "w-auto" : "w-[360px] max-w-[calc(100vw-24px)]",
        animate && "guide-pop-in",
        animate && !docked && "transition-[top,left] duration-300 ease-out",
      )}
    >
      <p aria-live="polite" className="sr-only">
        Step {index + 1} of {total}: {title}
      </p>

      <div className="flex items-start justify-between gap-3">
        <h2 id="guide-popover-title" className="text-md font-semibold leading-snug">
          {title}
        </h2>
        <button
          type="button"
          onClick={onSkip}
          className="-mr-1 -mt-1 shrink-0 rounded-sm px-1.5 py-0.5 text-xs text-muted hover:bg-surface hover:text-text"
          aria-label="Skip the guide"
        >
          Skip guide ✕
        </button>
      </div>

      {missingNote && (
        <p className="mt-2 rounded-sm border border-dashed border-border p-2 text-xs text-muted">{missingNote}</p>
      )}

      <p id="guide-popover-body" className="mt-2 text-sm leading-relaxed">
        {body}
      </p>

      {note && (
        <p className="mt-2 rounded-sm bg-surface p-2 text-xs leading-relaxed text-muted">
          <span className="font-medium text-text">How it works. </span>
          {note}
        </p>
      )}

      <div className="mt-4 flex items-center justify-between gap-3">
        {/* Dots read well up to ten steps; past that they become noise, so use a bar. */}
        {total <= 10 ? (
          <span className="flex items-center gap-1.5" aria-hidden>
            {Array.from({ length: total }).map((_, i) => (
              <span
                key={i}
                className={cn(
                  "h-1.5 rounded-full transition-all duration-200",
                  i === index ? "w-4 bg-accent" : i < index ? "w-1.5 bg-accent opacity-50" : "w-1.5 bg-border",
                )}
              />
            ))}
          </span>
        ) : (
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-border" aria-hidden>
            <span
              className="block h-full rounded-full bg-accent transition-all duration-300 ease-out"
              style={{ width: `${((index + 1) / total) * 100}%` }}
            />
          </span>
        )}
        <span className="tabular whitespace-nowrap text-xs text-muted">
          {index + 1} / {total}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <Button onClick={onBack} disabled={index === 0} className="flex-1">
          Back
        </Button>
        <Button variant="primary" onClick={onNext} className="flex-1">
          {isLast ? "Finish" : "Next"}
        </Button>
      </div>
    </div>
  );
}
