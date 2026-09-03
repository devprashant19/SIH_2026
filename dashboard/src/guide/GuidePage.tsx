import { useEffect, useMemo, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FilterBar, FilterSelect, FilterToggle } from "@/components/data/FilterBar";
import { Button, Card } from "@/components/ui/primitives";
import { useSearchParamState } from "@/state/useSearchParamState";
import { CONCEPTS } from "./concepts";
import { ControlCard } from "./components/ControlCard";
import { guide, type ControlKind } from "./model";
import { isResolvedRoute, withSearch } from "./nav";
import { useGuideStore } from "./useGuideStore";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";
import { CONTROL_KINDS, SCREENS, search, type AnchorEntry } from "./registry";

export function GuidePage() {
  const [params] = useSearchParams();
  const [q, setQ] = useSearchParamState("q", "");
  const [screenId] = useSearchParamState("screen", "");
  const [kind] = useSearchParamState("kind", "");
  const [traps] = useSearchParamState("traps", "");
  const [target] = useSearchParamState("guide", "");
  const startTour = useGuideStore((s) => s.startTour);
  const reduced = usePrefersReducedMotion();
  const searchRef = useRef<HTMLInputElement>(null);

  const hits = useMemo(
    () => search(q, { screenId: screenId || undefined, kind: (kind || undefined) as ControlKind | undefined, trapsOnly: traps === "1" }),
    [q, screenId, kind, traps],
  );

  const grouped = useMemo(() => {
    const bySection = new Map<string, AnchorEntry[]>();
    for (const hit of hits) {
      const list = bySection.get(hit.screen.id) ?? [];
      list.push(hit);
      bySection.set(hit.screen.id, list);
    }
    return SCREENS.filter((s) => bySection.has(s.id)).map((s) => ({ screen: s, entries: bySection.get(s.id)! }));
  }, [hits]);

  // ?guide=<anchor> scrolls to and focuses the card, which is how "Show me on the screen"
  // works in reverse: a link from anywhere into the explanation of one control.
  useEffect(() => {
    if (!target) return;
    const el = document.getElementById(`guide-${target}`) ?? document.getElementById(`guide-screen-${target}`);
    if (!el) return;
    el.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
    el.focus({ preventScroll: true });
  }, [target, reduced]);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">How this dashboard works</h1>
        <p className="max-w-3xl text-sm text-muted">
          Every control in the tool, what happens when you use it, and what it demonstrates. Press{" "}
          <kbd className="rounded-sm border border-border bg-surface px-1 font-mono text-xs">Shift + /</kbd> on any screen to
          open the same explanation for whatever you are looking at.
        </p>
      </header>

      <Card>
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted">Search</span>
            <input
              ref={searchRef}
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="threshold, uncertain, peer, export…"
              className="min-w-[220px] flex-1 rounded-sm border border-border bg-bg px-2 py-1"
              {...guide("guide.search")}
            />
            <span className="whitespace-nowrap text-xs text-muted">
              {hits.length} control{hits.length === 1 ? "" : "s"}
            </span>
            {(q || screenId || kind || traps) && (
              <Link className="text-xs text-accent hover:underline" to={{ pathname: "/guide", search: withSearch(params, { q: undefined, screen: undefined, kind: undefined, traps: undefined }) }}>
                Clear
              </Link>
            )}
          </label>
          <FilterBar>
            <FilterSelect
              label="Screen"
              param="screen"
              guide="guide.filter-screen"
              options={SCREENS.map((s) => ({ value: s.id, label: s.title }))}
            />
            <FilterSelect
              label="Kind"
              param="kind"
              guide="guide.filter-kind"
              options={CONTROL_KINDS.map((k) => ({ value: k, label: k.replace(/-/g, " ") }))}
            />
            <FilterToggle label="Watch out for these" param="traps" on="1" guide="guide.filter-traps" />
            <Button onClick={() => startTour("onboarding", 0)} {...guide("guide.tour-start")}>
              Take the guided tour
            </Button>
          </FilterBar>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <nav aria-label="Guide contents" className="hidden self-start lg:sticky lg:top-2 lg:block">
          <ul className="space-y-0.5 text-sm">
            {grouped.map(({ screen, entries }) => (
              <li key={screen.id}>
                <a href={`#guide-screen-${screen.id}`} className="flex items-baseline justify-between gap-2 rounded-sm px-2 py-1 hover:bg-accent-bg hover:text-accent">
                  <span>{screen.title}</span>
                  <span className="tabular text-xs text-muted">{entries.length}</span>
                </a>
              </li>
            ))}
            <li className="pt-1">
              <a href="#guide-concepts" className="block rounded-sm px-2 py-1 hover:bg-accent-bg hover:text-accent">
                Concepts
              </a>
            </li>
          </ul>
        </nav>

        <div className="space-y-4">
          {grouped.length === 0 && (
            <Card>
              <p className="text-sm text-muted">Nothing matches those words. Try a single word, or clear the filters.</p>
            </Card>
          )}

          {grouped.map(({ screen, entries }) => (
            <section key={screen.id} id={`guide-screen-${screen.id}`} tabIndex={-1} className="card p-3">
              <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-base font-semibold">{screen.title}</h2>
                {!screen.chrome && isResolvedRoute(screen.routePattern) && (
                  <Link className="text-sm text-accent hover:underline" to={{ pathname: screen.routePattern, search: withSearch(params, { q: undefined, screen: undefined, kind: undefined, traps: undefined, guide: undefined }) }}>
                    Open this screen
                  </Link>
                )}
              </header>
              <p className="text-sm">{screen.purpose}</p>
              <p className="mt-1 text-xs text-muted">
                Reached by: {screen.reachedBy.join(" ")}
                {screen.readsParams.length > 0 && (
                  <>
                    {" "}
                    Reads <span className="font-mono">{screen.readsParams.map((p) => `?${p}`).join(" ")}</span>.
                  </>
                )}
              </p>
              <ul className="mt-3 space-y-2">
                {entries.map((entry) => (
                  <ControlCard key={entry.anchor} entry={entry} highlighted={target === entry.anchor} />
                ))}
              </ul>
            </section>
          ))}

          <section id="guide-concepts" tabIndex={-1} className="card p-3" data-guide="guide.concepts">
            <h2 className="text-base font-semibold">Concepts</h2>
            <p className="mt-1 text-sm text-muted">The ideas the screens assume. Knowing what a button does is not the same as knowing why the tool works this way.</p>
            <dl className="mt-3 space-y-3">
              {CONCEPTS.map((c) => (
                <div key={c.id} id={`guide-concept-${c.id}`} className="rounded-md border border-border p-3">
                  <dt className="font-semibold">{c.term}</dt>
                  <dd className="mt-1 text-sm">{c.plain}</dd>
                  {c.formula && (
                    <dd className="mt-1.5 rounded-sm bg-surface px-2 py-1 font-mono text-xs">{c.formula}</dd>
                  )}
                </div>
              ))}
            </dl>
          </section>
        </div>
      </div>
    </div>
  );
}
