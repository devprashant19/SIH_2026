import { useFindings } from "@/api/hooks";
import { FilterBar, FilterSelect } from "@/components/data/FilterBar";
import { EntityPicker } from "@/components/data/Pickers";
import { DIMENSION_LABELS } from "@/components/charts/RiskHeatmap";
import { FindingsTable } from "@/components/domain/FindingsTable";
import { Card, QueryBoundary } from "@/components/ui/primitives";
import { periodOrUndefined, usePeriodParam, useSearchParamState } from "@/state/useSearchParamState";

export function FindingsListPage() {
  const [period] = usePeriodParam();
  const [entity] = useSearchParamState("entity", "");
  const [decision] = useSearchParamState("decision", "");
  const [dimension] = useSearchParamState("dimension", "");
  const [status] = useSearchParamState("status", "");
  const q = useFindings({
    period: periodOrUndefined(period),
    entity_id: entity || undefined,
    decision: decision || undefined,
    dimension: dimension || undefined,
    status: status || undefined,
    limit: 500,
  });
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Findings</h1>
        <p className="text-sm text-muted">Every supervisory indicator raised for the selected period, with its decision and review status.</p>
      </header>
      <Card
        title={<span className="text-sm font-semibold">{q.data ? `${q.data.total} findings` : "Findings"}</span>}
        actions={
          <FilterBar>
            <EntityPicker />
            <FilterSelect label="Dimension" param="dimension" guide="shared.dimension" options={Object.entries(DIMENSION_LABELS).map(([value, label]) => ({ value, label }))} />
            <FilterSelect label="Decision" param="decision" guide="shared.decision" options={[{ value: "AUTO_FLAG", label: "Flagged" }, { value: "MANUAL_REVIEW", label: "Uncertain" }, { value: "AUTO_CLEAR", label: "Cleared" }]} />
            <FilterSelect label="Status" param="status" guide="shared.status" options={[{ value: "open", label: "Open" }, { value: "reviewed", label: "Reviewed" }, { value: "uncertain", label: "Uncertain" }]} />
          </FilterBar>
        }
      >
        <QueryBoundary query={q} rows={8}>
          {(d) => <FindingsTable items={d.items} period={period} showEntity tableGuide="findings.table" firstRowGuide="findings.row" emptyHint="Clear a filter or choose another period." />}
        </QueryBoundary>
      </Card>
    </div>
  );
}
