import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** Filter state lives in the URL so every view is deep-linkable and the back button works. */
export function useSearchParamState(key: string, fallback = ""): [string, (v: string | undefined) => void] {
  const [params, setParams] = useSearchParams();
  const value = params.get(key) ?? fallback;
  const set = useCallback(
    (v: string | undefined) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (v === undefined || v === "" || v === fallback) next.delete(key);
          else next.set(key, v);
          return next;
        },
        { replace: true },
      );
    },
    [key, fallback, setParams],
  );
  return [value, set];
}

/** The globally selected submission period; "latest" means "whatever the API considers current". */
export function usePeriodParam(): [string, (v: string | undefined) => void] {
  return useSearchParamState("period", "latest");
}

export function periodOrUndefined(period: string): string | undefined {
  return period && period !== "latest" ? period : undefined;
}
