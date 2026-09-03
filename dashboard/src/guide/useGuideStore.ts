import { create } from "zustand";

/**
 * Guide state: whether the help panel is open, and where a tour has got to.
 *
 * Kept out of uiStore because that store documents in-file that it holds only transient UI
 * state, and this one persists a little. Action identities are stable for the store's lifetime,
 * which is what lets closeHelp be handed straight to Drawer's onClose without re-triggering its
 * effect on every render.
 */

export type TourStatus = "idle" | "preparing" | "resolving" | "showing" | "missing" | "off-route";

const KEY_TOUR = "satsa.guide.tour";
const KEY_NUDGE = "satsa.guide.nudge";

function read(key: string, fallback = ""): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage may be unavailable */
  }
}

function parseSeen(raw: string): Record<string, string> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, string>) : {};
  } catch {
    return {};
  }
}

// Read at module scope, which happens once even under StrictMode's double mount.
const INITIAL_SEEN = parseSeen(read(KEY_TOUR));
const INITIAL_NUDGE = read(KEY_NUDGE) === "dismissed";

interface GuideState {
  helpOpen: boolean;
  openHelp: () => void;
  closeHelp: () => void;
  toggleHelp: () => void;

  tourId: string | null;
  stepIndex: number;
  status: TourStatus;
  /** Restored when the tour ends, because a tour may expand the nav to reach a control. */
  navCollapsedAtStart: boolean | null;

  startTour: (id: string, at?: number) => void;
  goToStep: (i: number) => void;
  endTour: (reason: "finished" | "skipped") => void;
  setStatus: (s: TourStatus) => void;
  setNavCollapsedAtStart: (v: boolean | null) => void;

  seenTours: Record<string, string>;
  nudgeDismissed: boolean;
  dismissNudge: () => void;
}

export const useGuideStore = create<GuideState>((set, get) => ({
  helpOpen: false,
  openHelp: () => set({ helpOpen: true }),
  closeHelp: () => set({ helpOpen: false }),
  toggleHelp: () => set((s) => ({ helpOpen: !s.helpOpen })),

  tourId: null,
  stepIndex: 0,
  status: "idle",
  navCollapsedAtStart: null,

  startTour: (id, at = 0) => set({ tourId: id, stepIndex: at, status: "preparing", helpOpen: false }),
  goToStep: (i) => set({ stepIndex: Math.max(0, i), status: "preparing" }),
  endTour: (reason) => {
    const { tourId, stepIndex, seenTours } = get();
    if (tourId && tourId !== "__single") {
      const next = { ...seenTours, [tourId]: reason === "finished" ? "completed" : `at:${stepIndex}` };
      write(KEY_TOUR, JSON.stringify(next));
      set({ seenTours: next });
    }
    set({ tourId: null, stepIndex: 0, status: "idle" });
  },
  setStatus: (status) => set({ status }),
  setNavCollapsedAtStart: (navCollapsedAtStart) => set({ navCollapsedAtStart }),

  seenTours: INITIAL_SEEN,
  nudgeDismissed: INITIAL_NUDGE,
  dismissNudge: () => {
    write(KEY_NUDGE, "dismissed");
    set({ nudgeDismissed: true });
  },
}));
