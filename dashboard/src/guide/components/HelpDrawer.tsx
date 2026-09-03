import { useLocation } from "react-router-dom";
import { Button, Drawer } from "@/components/ui/primitives";
import { CONCEPTS } from "../concepts";
import { guide } from "../model";
import { controlsFor, GLOBAL_SCREEN, screenForPath } from "../registry";
import { useGuideStore } from "../useGuideStore";
import { ControlCard } from "./ControlCard";

/**
 * The contextual half of the guide: every control on the screen you are actually looking at.
 * Mounted once in TourController, so it takes no props and reads the router itself, the same
 * convention Toasts follows.
 */
export function HelpDrawer({ onShowMe }: { onShowMe: (anchor: string) => void }) {
  const { pathname } = useLocation();
  const helpOpen = useGuideStore((s) => s.helpOpen);
  // A stable action identity, so Drawer's effect runs once per open rather than every render.
  const closeHelp = useGuideStore((s) => s.closeHelp);
  const startTour = useGuideStore((s) => s.startTour);

  const screen = screenForPath(pathname);
  const entries = screen ? controlsFor(screen) : [];
  const globalEntries = controlsFor(GLOBAL_SCREEN);
  const conceptIds = new Set([...(screen?.concepts ?? []), ...entries.flatMap((e) => e.control.concepts ?? [])]);
  const concepts = CONCEPTS.filter((c) => conceptIds.has(c.id));

  return (
    <Drawer open={helpOpen} onClose={closeHelp} width="max-w-lg" title={`Help · ${screen?.title ?? "This screen"}`}>
      {screen ? (
        <div className="space-y-3">
          <p className="text-sm">{screen.purpose}</p>

          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => startTour("onboarding", 0)}>
              Take the guided tour
            </Button>
          </div>

          <ul className="space-y-2">
            {entries.map((entry) => (
              <ControlCard key={entry.anchor} entry={entry} compact onShowMe={onShowMe} />
            ))}
          </ul>

          {concepts.length > 0 && (
            <details className="rounded-md border border-border p-2">
              <summary className="cursor-pointer text-sm font-medium">Ideas this screen assumes</summary>
              <dl className="mt-2 space-y-2">
                {concepts.map((c) => (
                  <div key={c.id}>
                    <dt className="text-sm font-medium">{c.term}</dt>
                    <dd className="text-sm text-muted">{c.plain}</dd>
                    {c.formula && <dd className="mt-1 rounded-sm bg-surface px-2 py-1 font-mono text-xs">{c.formula}</dd>}
                  </div>
                ))}
              </dl>
            </details>
          )}

          <details className="rounded-md border border-border p-2">
            <summary className="cursor-pointer text-sm font-medium">On every screen</summary>
            <ul className="mt-2 space-y-2">
              {globalEntries.map((entry) => (
                <ControlCard key={entry.anchor} entry={entry} compact onShowMe={onShowMe} />
              ))}
            </ul>
          </details>
        </div>
      ) : (
        <p className="text-sm text-muted">This path has no guide entry.</p>
      )}
    </Drawer>
  );
}

/** The `?` button in the top bar. */
export function HelpButton() {
  const helpOpen = useGuideStore((s) => s.helpOpen);
  const toggleHelp = useGuideStore((s) => s.toggleHelp);
  return (
    <Button
      variant="ghost"
      aria-label="Help for this screen"
      aria-keyshortcuts="Shift+Slash"
      aria-expanded={helpOpen}
      title="Help for this screen (Shift + /)"
      onClick={toggleHelp}
      {...guide("global.help")}
    >
      ?
    </Button>
  );
}
