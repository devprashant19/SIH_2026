import { create } from "zustand";

// Only transient UI state lives here. Filters and the selected period live in the URL so
// every view is deep-linkable; server data lives in TanStack Query.
interface UiState {
  navCollapsed: boolean;
  toggleNav: () => void;
  toasts: { id: number; text: string; tone?: "info" | "error" }[];
  pushToast: (text: string, tone?: "info" | "error") => void;
  dismissToast: (id: number) => void;
}

let toastSeq = 0;

export const useUiStore = create<UiState>((set) => ({
  navCollapsed: false,
  toggleNav: () => set((s) => ({ navCollapsed: !s.navCollapsed })),
  toasts: [],
  pushToast: (text, tone = "info") =>
    set((s) => ({ toasts: [...s.toasts, { id: ++toastSeq, text, tone }] })),
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
