import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function current(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches;
}

/**
 * globals.css already clamps every CSS transition when the user asks for reduced motion.
 * This hook covers the parts JavaScript controls: smooth scrolling, and the short waits the
 * tour spends letting a scroll or a nav transition settle before it measures.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(current);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(QUERY);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}
