import { useEntities, useTrendControls, useTrendEntity, useTrendSector } from "@/api/hooks";
import { TrendChart } from "@/components/charts/TrendChart";
import { FilterBar, FilterSelect } from "@/components/data/FilterBar";
import { SectorPicker } from "@/components/data/Pickers";
import { Card, QueryBoundary } from "@/components/ui/primitives";
import { DIMENSION_LABELS } from "@/components/charts/RiskHeatmap";
import { useSearchParamState } from "@/state/useSearchParamState";
import type { SriDimension } from "@/api/types";

export function TrendsPage() {
  const [sector] = useSearchParamState("sector", "");
  const [entity] = useSearchParamState("entity", "");
  const entities = useEntities();
  const sectorTrend = useTrendSector(sector || undefined);
  const entityTrend = useTrendEntity(entity || "");
  const controls = useTrendControls();

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Trends</h1>
        <p className="text-sm text-muted">How supervisory risk moves across submission periods, for the portfolio and for a single entity.</p>
      </header>

      <FilterBar>
        <SectorPicker />
        <QueryBoundary query={entities} rows={1}>
          {(list) => <FilterSelect label="Entity detail" param="entity" options={list.map((e) => ({ value: e.entity_id, label: `${e.entity_id} · ${e.name}` }))} />}
        </QueryBoundary>
      </FilterBar>

      <Card title="Supervisory Risk Indicator by entity">
        <QueryBoundary query={sectorTrend} rows={6}>
          {(t) => {
            const ids = Object.keys(t.entities).slice(0, 6);
            return (
              <TrendChart
                periods={t.periods}
                series={[
                  ...ids.map((id) => ({ key: id, label: id, values: t.entities[id] })),
                  { key: "median", label: "Sector median", values: t.median_sri, dashed: true },
                ]}
                caption={`SRI by entity with the ${sector || "portfolio"} median across ${t.periods.length} periods.`}
                yLabel="SRI"
                height={260}
              />
            );
          }}
        </QueryBoundary>
      </Card>

      {entity && (
        <Card title={`${entity} · dimension breakdown`}>
          <QueryBoundary query={entityTrend} rows={6}>
            {(t) => (
              <TrendChart
                periods={t.periods}
                series={(Object.keys(DIMENSION_LABELS) as SriDimension[]).map((d) => ({ key: d, label: DIMENSION_LABELS[d], values: t.dims[d] ?? [] }))}
                caption={`Each SRI dimension for ${entity} across ${t.periods.length} periods.`}
                yLabel="Dimension score"
                height={240}
              />
            )}
          </QueryBoundary>
        </Card>
      )}

      <Card title="Control priorities over time" actions={<span className="text-xs text-muted">Which processes are failing across the portfolio</span>}>
        <QueryBoundary query={controls} rows={6}>
          {(t) => (
            <TrendChart
              periods={t.periods}
              series={t.controls.slice(0, 6).map((c) => ({ key: c.control_id, label: c.label, values: c.series }))}
              caption="Expected cost of the findings attributed to each control, per period."
              yLabel="Priority"
              height={240}
            />
          )}
        </QueryBoundary>
      </Card>
    </div>
  );
}
