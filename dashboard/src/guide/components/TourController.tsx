import { useCallback, useEffect, useRef, useState } from "react";
import { matchPath, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useUiStore } from "@/state/uiStore";
import { popLayer, pushLayer } from "../layers";
import { formatTourParam, isResolvedRoute, parseTourParam, withSearch } from "../nav";
import { BY_ANCHOR } from "../registry";
import { TOUR_BY_ID, type TourStep } from "../tours";
import { rectOf, resolveAnchor, sameRect, waitForAnchor } from "../useAnchor";
import { useGuideStore } from "../useGuideStore";
import { usePrefersReducedMotion } from "../usePrefersReducedMotion";
import type { Rect } from "../usePlacement";
import { GuidePopover } from "./GuidePopover";
import { GuideSpotlight } from "./GuideSpotlight";
import { HelpDrawer } from "./HelpDrawer";

/** One instance, mounted in AppShell beside <Toasts />. Owns the help panel and the tour. */
export function TourController() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const reduced = usePrefersReducedMotion();
  const pushToast = useUiStore((s) => s.pushToast);

  const helpOpen = useGuideStore((s) => s.helpOpen);
  const closeHelp = useGuideStore((s) => s.closeHelp);
  const toggleHelp = useGuideStore((s) => s.toggleHelp);
  const tourId = useGuideStore((s) => s.tourId);
  const stepIndex = useGuideStore((s) => s.stepIndex);
  const startTour = useGuideStore((s) => s.startTour);
  const goToStep = useGuideStore((s) => s.goToStep);
  const endTour = useGuideStore((s) => s.endTour);

  const [rect, setRect] = useState<Rect | null>(null);
  const [missingNote, setMissingNote] = useState<string | undefined>(undefined);
  // Off-route is only meaningful once the step has finished navigating and resolving.
  const [preparing, setPreparing] = useState(false);
  const [singleAnchor, setSingleAnchor] = useState<string | null>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);
  // Synthetic clicks already performed, keyed by tour, step and anchor. A click usually
  // navigates, which re-runs the effect, and without this the tour would click again or
  // wait pointlessly for a control that only existed on the previous screen.
  const doneActions = useRef<Set<string>>(new Set());

  const tour = tourId && tourId !== "__single" ? TOUR_BY_ID.get(tourId) : undefined;
  const step: TourStep | undefined = tour?.steps[stepIndex];
  const active = !!tourId;
  const onRoute = preparing || !step || !!matchPath({ path: step.routePattern, end: true }, pathname);

  // ---- keyboard: Shift+/ opens help, guarded against text fields -------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "?" || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      const t = e.target as HTMLElement | null;
      if (t && (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement || t.isContentEditable)) return;
      e.preventDefault();
      toggleHelp();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggleHelp]);

  // ---- Escape layers: the tour sits above the help panel, which sits above a Drawer -------
  useEffect(() => {
    if (!helpOpen) return;
    const id = pushLayer(closeHelp);
    return () => popLayer(id);
  }, [helpOpen, closeHelp]);

  const finish = useCallback(
    (reason: "finished" | "skipped") => {
      const { navCollapsedAtStart, setNavCollapsedAtStart } = useGuideStore.getState();
      const ui = useUiStore.getState();
      if (navCollapsedAtStart !== null && ui.navCollapsed !== navCollapsedAtStart) ui.toggleNav();
      setNavCollapsedAtStart(null);
      endTour(reason);
      doneActions.current.clear();
      setSingleAnchor(null);
      setRect(null);
      navigate({ pathname, search: withSearch(params, { tour: undefined }) }, { replace: true });
      queueMicrotask(() => {
        const saved = restoreFocus.current;
        if (saved && document.contains(saved)) saved.focus();
        else document.querySelector<HTMLElement>('[data-guide="global.help"]')?.focus();
        restoreFocus.current = null;
      });
    },
    [endTour, navigate, pathname, params],
  );

  useEffect(() => {
    if (!active) return;
    const id = pushLayer(() => finish("skipped"));
    return () => popLayer(id);
  }, [active, finish]);

  // ---- URL is the authority for tour position; the store mirrors it ----------------------
  useEffect(() => {
    const parsed = parseTourParam(params.get("tour"));
    const s = useGuideStore.getState();
    if (parsed && TOUR_BY_ID.has(parsed.id)) {
      if (s.tourId !== parsed.id) s.startTour(parsed.id, parsed.step);
      else if (s.stepIndex !== parsed.step) s.goToStep(parsed.step);
    } else if (s.tourId && s.tourId !== "__single") {
      // The app navigated on its own, for instance a heatmap cell opening an entity, and
      // rebuilt the query string without the tour. Put it back so a reload still resumes.
      navigate({ pathname, search: withSearch(params, { tour: formatTourParam(s.tourId, s.stepIndex) }) }, { replace: true });
    }
  }, [params, pathname, navigate]);

  // Remember the nav state so a tour that expands the rail can put it back.
  useEffect(() => {
    if (!active) return;
    const s = useGuideStore.getState();
    if (s.navCollapsedAtStart === null) s.setNavCollapsedAtStart(useUiStore.getState().navCollapsed);
  }, [active]);

  // ---- prepare and resolve the current step ----------------------------------------------
  useEffect(() => {
    if (!active) return;
    const anchor = singleAnchor ?? step?.anchor;
    if (!anchor) return;

    let cancelled = false;
    let pending: { cancel: () => void } | null = null;

    const run = async () => {
      setMissingNote(undefined);
      setPreparing(true);

      // The nav rail keeps its links when collapsed, but a tour that points at one should
      // show the label it is naming.
      if (step?.before?.some((a) => a.type === "expandNav")) {
        const ui = useUiStore.getState();
        if (ui.navCollapsed) ui.toggleNav();
      }

      for (const action of step?.before ?? []) {
        if (cancelled) return;
        if (action.type === "navigate" && !matchPath({ path: action.to, end: true }, pathname)) {
          navigate({ pathname: action.to, search: withSearch(params, { ...action.params, tour: formatTourParam(tourId!, stepIndex) }) }, { replace: true });
          return; // the navigation re-runs this effect
        }
        if (action.type === "setParam") {
          // Only navigate when the value actually changes, or the effect re-runs for ever.
          const current = params.get(action.key);
          const wanted = action.value ?? null;
          if (current !== wanted && !(current === null && wanted === null)) {
            navigate({ pathname, search: withSearch(params, { [action.key]: action.value }) }, { replace: true });
            return;
          }
        }
        if (action.type === "click") {
          const key = `${tourId}.${stepIndex}.${action.anchor}`;
          if (doneActions.current.has(key)) continue;
          // Synthesised so a step can open a drawer or drill into a row on the user's behalf.
          // The target usually sits behind a query, so wait for it rather than clicking into a
          // skeleton. If it never appears, onMissing takes over and the tour does not hang.
          const target = await waitForAnchor(action.anchor, 2500).promise;
          if (cancelled) return;
          doneActions.current.add(key);
          if (target) {
            target.click();
            return; // a click usually navigates; let the effect re-run on the new route
          }
        }
      }

      const control = BY_ANCHOR.get(anchor)?.control;
      // A control that is always present should be explained if it is somehow missing; one that
      // depends on data should be skipped, so the tour completes on an empty database.
      const policy = step?.onMissing ?? ((control?.availability ?? "always") === "always" ? "explain" : "skip");
      const waiter = waitForAnchor(anchor, policy === "wait" ? 0 : 1500);
      pending = waiter;
      const el = await waiter.promise;
      if (cancelled) return;

      setPreparing(false);
      if (!el) {
        if (policy === "skip" && step && tour && stepIndex + 1 < tour.steps.length) {
          goToStep(stepIndex + 1);
          return;
        }
        setRect(null);
        setMissingNote(control?.requires ? `This control appears once ${control.requires}.` : "This control is not on the screen right now.");
        return;
      }

      el.scrollIntoView({ block: "center", inline: "nearest", behavior: reduced ? "auto" : "smooth" });
      setRect(rectOf(el));
    };

    void run();
    return () => {
      cancelled = true;
      pending?.cancel();
    };
    // pathname and params are needed so the effect re-runs after a navigation action.
  }, [active, singleAnchor, step, stepIndex, tour, tourId, pathname, params, navigate, goToStep, reduced]);

  // ---- keep the rect current while the page scrolls, resizes or re-renders ----------------
  useEffect(() => {
    if (!active) return;
    const anchor = singleAnchor ?? step?.anchor;
    if (!anchor) return;
    let frame = 0;
    const measure = () => {
      frame = 0;
      const el = resolveAnchor(anchor);
      const next = el ? rectOf(el) : null;
      setRect((prev) => (sameRect(prev, next) ? prev : next));
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    const ro = new ResizeObserver(schedule);
    ro.observe(document.body);
    const mo = new MutationObserver(schedule);
    mo.observe(document.body, { childList: true, subtree: true, attributes: true });
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      ro.disconnect();
      mo.disconnect();
    };
  }, [active, singleAnchor, step]);

  const showMe = useCallback(
    (anchor: string) => {
      restoreFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      closeHelp();
      startTour("__single", 0);
      setSingleAnchor(anchor);
    },
    [closeHelp, startTour],
  );

  const next = useCallback(() => {
    if (singleAnchor || !tour) return finish("finished");
    if (stepIndex + 1 >= tour.steps.length) return finish("finished");
    const i = stepIndex + 1;
    goToStep(i);
    navigate({ pathname, search: withSearch(params, { tour: formatTourParam(tour.id, i) }) }, { replace: true });
  }, [singleAnchor, tour, stepIndex, goToStep, navigate, pathname, params, finish]);

  const back = useCallback(() => {
    if (!tour || stepIndex === 0) return;
    const i = stepIndex - 1;
    goToStep(i);
    navigate({ pathname, search: withSearch(params, { tour: formatTourParam(tour.id, i) }) }, { replace: true });
  }, [tour, stepIndex, goToStep, navigate, pathname, params]);

  // A first-time nudge, never an auto-start. Seizing the screen of someone evaluating a
  // supervisory tool would be hostile.
  const nudged = useRef(false);
  useEffect(() => {
    if (nudged.current) return;
    nudged.current = true;
    const s = useGuideStore.getState();
    if (s.seenTours.onboarding || s.nudgeDismissed) return;
    s.dismissNudge();
    pushToast("New here? Press ? for help on any screen, or open How this works for a guided tour.");
  }, [pushToast]);

  const single = singleAnchor ? BY_ANCHOR.get(singleAnchor) : undefined;

  return (
    <>
      <HelpDrawer onShowMe={showMe} />
      {active && (
        <>
          <GuideSpotlight rect={rect} padding={step?.padding ?? 6} animate={!reduced} />
          {single ? (
            <GuidePopover
              rect={rect}
              title={single.control.label}
              body={single.control.does}
              missingNote={missingNote}
              index={0}
              total={1}
              animate={!reduced}
              onNext={() => finish("finished")}
              onBack={() => finish("finished")}
              onSkip={() => finish("skipped")}
            />
          ) : (
            step &&
            tour && (
              <GuidePopover
                rect={onRoute ? rect : null}
                title={onRoute ? step.title : "You have left the tour"}
                body={
                  onRoute
                    ? step.body
                    : isResolvedRoute(step.routePattern)
                      ? "Press Next to go back to where the tour was, or end it and carry on on your own."
                      : "This step was about a specific record you have navigated away from. End the tour, or press Back to step to somewhere it can reach."
                }
                missingNote={onRoute ? missingNote : undefined}
                index={stepIndex}
                total={tour.steps.length}
                prefer={step.prefer}
                animate={!reduced}
                onNext={
                  onRoute
                    ? next
                    : isResolvedRoute(step.routePattern)
                      ? () => navigate({ pathname: step.routePattern, search: withSearch(params, { tour: formatTourParam(tour.id, stepIndex) }) }, { replace: true })
                      : () => finish("skipped")
                }
                onBack={back}
                onSkip={() => finish("skipped")}
              />
            )
          )}
        </>
      )}
    </>
  );
}
