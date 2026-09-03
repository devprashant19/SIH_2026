import { useState } from "react";
import { cn } from "@/lib/cn";
import { TOURS } from "../tours";
import { useGuideStore } from "../useGuideStore";

/**
 * The floating trigger, fixed bottom-left on every screen. One tour today, so a single click
 * starts it; if a second is ever added the button opens a small menu instead of guessing.
 */
export function TourLauncher() {
  const [menuOpen, setMenuOpen] = useState(false);
  const tourId = useGuideStore((s) => s.tourId);
  const startTour = useGuideStore((s) => s.startTour);
  const seenTours = useGuideStore((s) => s.seenTours);

  // Hidden while a tour is running: the popover already owns Back, Next and Skip.
  if (tourId) return null;

  const single = TOURS.length === 1 ? TOURS[0] : null;
  const unseen = TOURS.some((t) => !seenTours[t.id]);

  return (
    <div className="fixed bottom-4 left-4 z-toast print:hidden">
      {menuOpen && !single && (
        <ul className="mb-2 w-64 overflow-hidden rounded-md border border-border bg-bg shadow-drawer">
          {TOURS.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  startTour(t.id, 0);
                }}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-accent-bg hover:text-accent"
              >
                <span className="font-medium">{t.title}</span>
                <span className="mt-0.5 block text-xs text-muted">{t.steps.length} steps</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        // `group` drives the label that slides out on hover, and `peer` is not used because
        // the label sits inside the button so a touch anywhere on it still starts the tour.
        className={cn(
          "group flex items-center gap-0 rounded-full border border-border bg-bg py-2 pl-2 pr-2 shadow-drawer",
          "transition-all duration-200 hover:border-accent hover:pr-3 hover:text-accent focus-visible:border-accent",
        )}
        aria-label={single ? `Take a tour: ${single.title}` : "Take a tour"}
        title="Take a tour"
        aria-expanded={single ? undefined : menuOpen}
        onClick={() => (single ? startTour(single.id, 0) : setMenuOpen((o) => !o))}
      >
        <span className="relative grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-bg text-base font-semibold text-accent">
          <span aria-hidden>?</span>
          {unseen && (
            // A quiet dot rather than a pulsing badge: this is a supervisory tool.
            <span aria-hidden className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-accent ring-2 ring-bg" />
          )}
        </span>
        <span className="max-w-0 overflow-hidden whitespace-nowrap text-sm font-medium transition-all duration-200 group-hover:ml-2 group-hover:max-w-[8rem] group-focus-visible:ml-2 group-focus-visible:max-w-[8rem]">
          Take a tour
        </span>
      </button>
    </div>
  );
}
