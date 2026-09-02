import { useEntities, usePeriods } from "@/api/hooks";
import { Select } from "@/components/ui/primitives";
import { usePeriodParam, useSearchParamState } from "@/state/useSearchParamState";

export function PeriodPicker() {
  const { data } = usePeriods();
  const [period, setPeriod] = usePeriodParam();
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor="period-picker" className="text-muted">
        Period
      </label>
      <Select id="period-picker" value={period} onChange={(e) => setPeriod(e.target.value)} data-testid="period-picker">
        <option value="latest">Latest</option>
        {(data ?? []).map((p) => (
          <option key={p.period} value={p.period}>
            {p.period}
          </option>
        ))}
      </Select>
    </span>
  );
}

export function EntityPicker({ param = "entity", label = "Entity" }: { param?: string; label?: string }) {
  const { data } = useEntities();
  const [value, setValue] = useSearchParamState(param, "");
  const id = `entity-${param}`;
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor={id} className="text-muted">
        {label}
      </label>
      <Select id={id} value={value} onChange={(e) => setValue(e.target.value)}>
        <option value="">All</option>
        {(data ?? []).map((e) => (
          <option key={e.entity_id} value={e.entity_id}>
            {e.entity_id} · {e.name}
          </option>
        ))}
      </Select>
    </span>
  );
}

export function SectorPicker() {
  const { data } = useEntities();
  const sectors = Array.from(new Set((data ?? []).map((e) => e.sector))).sort();
  const [value, setValue] = useSearchParamState("sector", "");
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor="sector-picker" className="text-muted">
        Sector
      </label>
      <Select id="sector-picker" value={value} onChange={(e) => setValue(e.target.value)}>
        <option value="">All</option>
        {sectors.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </Select>
    </span>
  );
}
