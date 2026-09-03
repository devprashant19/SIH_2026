import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { place, type Placement, type Rect, type Side } from "../usePlacement";

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export interface GuidePopoverProps {
  rect: Rect | null;
  title: string;
  body: string;
  /** Set when the anchor could not be found and the step chose to explain rather than skip. */
  missingNote?: string;
  index: number;
  total: number;
  prefer?: readonly Side[];
  animate?: boolean;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}

export function GuidePopover({ rect, title, body, missingNote, index, total, prefer, animate = true, onNext, onBack, onSkip }: GuidePopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const centred = rect === null;

  // Two-pass measurement: render hidden, measure, place, paint once.
  useLayoutEffect(() => {
    if (!ref.current || !rect) {
      setPlacement(null);
      return;
    }
    const box = ref.current.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = document.documentElement.clientHeight;
    setPlacement(place(rect, { w: box.width, h: box.height }, { w: vw, h: vh }, prefer));
  }, [rect, prefer, title, body]);

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

  const style: React.CSSProperties = centred
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
      style={{ ...style, maxHeight: "calc(100vh - 24px)", maxWidth: "min(360px, calc(100vw - 24px))" }}
      className={cn(
        "fixed z-guide-popover w-[360px] overflow-auto rounded-md border border-border bg-bg p-3 shadow-drawer",
        animate && !centred && "transition-[top,left] duration-150",
      )}
    >
      <p aria-live="polite" className="sr-only">
        Step {index + 1} of {total}: {title}
      </p>

      <div className="flex items-baseline justify-between gap-2">
        <h2 id="guide-popover-title" className="text-sm font-semibold">
          {title}
        </h2>
        <span className="tabular whitespace-nowrap text-xs text-muted">
          {index + 1} of {total}
        </span>
      </div>

      {missingNote && <p className="mt-1.5 rounded-sm border border-dashed border-border p-2 text-xs text-muted">{missingNote}</p>}

      <p id="guide-popover-body" className="mt-1.5 text-sm">
        {body}
      </p>

      <div className="mt-2 flex gap-0.5" aria-hidden>
        {Array.from({ length: total }).map((_, i) => (
          <span key={i} className={cn("h-1 flex-1 rounded-sm", i <= index ? "bg-accent" : "bg-surface")} />
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        <Button variant="ghost" onClick={onSkip}>
          End tour
        </Button>
        <span className="flex gap-2">
          <Button onClick={onBack} disabled={index === 0}>
            Back
          </Button>
          <Button variant="primary" onClick={onNext}>
            {index + 1 === total ? "Done" : "Next"}
          </Button>
        </span>
      </div>
      <p className="mt-1.5 text-xs text-muted">
        Use Back rather than the browser's back button, which leaves the tour. Escape ends it.
      </p>
    </div>
  );
}
