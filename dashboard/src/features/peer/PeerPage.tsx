import { Link } from "react-router-dom";
import { useBenchmark, useBenchmarkMetrics, useBenchmarkRank } from "@/api/hooks";
import { PeerDistributionChart } from "@/components/charts/PeerDistributionChart";
import { FilterBar, FilterSelect } from "@/components/data/FilterBar";
import { EntityPicker, SectorPicker } from "@/components/data/Pickers";
import { RiskBadge } from "@/components/domain/badges";
import { Card, QueryBoundary } from "@/components/ui/primitives";
import { guide } from "@/guide/model";
import { fmt1, fmt2 } from "@/lib/format";
import { periodOrUndefined, usePeriodParam, useSearchParamState } from "@/state/useSearchParamState";

export function PeerPage() {
  const [period] = usePeriodParam();
  const [metric] = useSearchParamState("metric", "escalation_ratio_critical");
  const [entity, setEntity] = useSearchParamState("entity", "");
  const [sector] = useSearchParamState("sector", "");
  const p = periodOrUndefined(period);
  const metrics = useBenchmarkMetrics();
  const bench = useBenchmark(metric || "escalation_ratio_critical", p, entity || undefined);
  const rank = useBenchmarkRank(p, sector || undefined);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Peer benchmarking</h1>
        <p className="text-sm text-muted">Every metric is compared inside a peer group of the same sector and size band, falling back to a wider group when the sector is too small.</p>
      </header>

      <FilterBar>
        <QueryBoundary query={metrics} rows={1}>
          {(m) => <FilterSelect label="Metric" param="metric" guide="shared.metric" fallback="escalation_ratio_critical" options={m.filter((x) => x.headline).map((x) => ({ value: x.key, label: x.label }))} />}
        </QueryBoundary>
        <EntityPicker label="Highlight" />
        <SectorPicker />
      </FilterBar>

      <Card title="Distribution across peers">
        <QueryBoundary query={bench} rows={4}>
          {(b) => (
            <div className="space-y-2">
              <div {...guide("peer.chart")}>
                <PeerDistributionChart data={b} entityId={entity || undefined} height={170} onSelect={setEntity} />
              </div>
              <p className="text-sm text-muted" {...guide("peer.peer-level")}>
                Peer group {b.peer_group_id} (level {b.peer_level}, {b.stats.n} entities). {entity && b.entity_value != null ? `${entity} is at ${fmt2(b.entity_value)} against a median of ${fmt2(b.stats.median)}.` : "Select an entity to mark it on the chart."}
              </p>
            </div>
          )}
        </QueryBoundary>
      </Card>

      <Card title="Rank table" actions={<span className="text-xs text-muted">Values with their percentile inside the peer group</span>}>
        <QueryBoundary query={rank} rows={6}>
          {(r) => (
            <div className="overflow-x-auto" {...guide("peer.rank-table")}>
              <table className="w-full text-sm">
                <caption className="sr-only">Entity ranking across headline metrics</caption>
                <thead>
                  <tr>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Entity</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">SRI</th>
                    {r.features.map((f) => (
                      <th key={f.key} scope="col" className="border-b border-border px-2 py-1 text-left" title={`${f.label} (${f.higher_is_worse ? "higher is worse" : "lower is worse"})`}>
                        {f.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.rows.map((row) => (
                    <tr key={row.entity_id} className="border-b border-border hover:bg-surface">
                      <td className="px-2 py-1.5">
                        <Link to={{ pathname: `/entities/${row.entity_id}`, search: `?period=${period}` }} className="text-accent hover:underline">
                          {row.entity_id}
                        </Link>
                        <div className="text-xs text-muted">{row.sector}</div>
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5">
                        <span className="tabular">{fmt1(row.sri)}</span> <RiskBadge band={row.band} compact />
                      </td>
                      {r.features.map((f) => {
                        const pct = row.percentiles[f.key];
                        const risky = pct != null && (f.higher_is_worse ? pct > 0.75 : pct < 0.25);
                        return (
                          <td key={f.key} className={`tabular px-2 py-1.5 ${risky ? "text-risk-high" : ""}`} title={pct != null ? `${Math.round(pct * 100)}th percentile` : "not available"}>
                            {fmt2(row.values[f.key])}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryBoundary>
      </Card>
    </div>
  );
}
