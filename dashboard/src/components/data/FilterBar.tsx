import type { ReactNode } from "react";
import { Select } from "@/components/ui/primitives";
import { useSearchParamState } from "@/state/useSearchParamState";

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2 text-sm">{children}</div>;
}

/** A select whose value is stored in the URL, so filters survive reload and can be shared. */
export function FilterSelect({ label, param, options, fallback = "", guide }: { label: string; param: string; options: { value: string; label: string }[]; fallback?: string; guide?: string }) {
  const [value, setValue] = useSearchParamState(param, fallback);
  const id = `filter-${param}`;
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor={id} className="text-muted">
        {label}
      </label>
      <Select id={id} value={value} onChange={(e) => setValue(e.target.value)} data-guide={guide}>
        <option value={fallback}>All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    </span>
  );
}

export function FilterToggle({ label, param, on = "1", guide }: { label: string; param: string; on?: string; guide?: string }) {
  const [value, setValue] = useSearchParamState(param, "");
  const id = `toggle-${param}`;
  return (
    <span className="inline-flex items-center gap-1">
      <input id={id} type="checkbox" checked={value === on} onChange={(e) => setValue(e.target.checked ? on : undefined)} data-guide={guide} />
      <label htmlFor={id}>{label}</label>
    </span>
  );
}
