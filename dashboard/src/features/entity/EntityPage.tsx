import { Link, useParams } from "react-router-dom";
import { useBenchmark, useEntity, useFindings, useTrendEntity } from "@/api/hooks";
import { endpoints, download } from "@/api/endpoints";
import { PeerDistributionChart } from "@/components/charts/PeerDistributionChart";
import { DIMENSION_LABELS } from "@/components/charts/RiskHeatmap";
import { BulletBar, ScoreBar } from "@/components/charts/primitives";
import { TrendChart } from "@/components/charts/TrendChart";
import { FilterBar, FilterSelect } from "@/components/data/FilterBar";
import { FindingsTable } from "@/components/domain/FindingsTable";
import { RiskBadge, SupportBadge } from "@/components/domain/badges";
import { Button, Card, HashChip, QueryBoundary } from "@/components/ui/primitives";
import { guide } from "@/guide/model";
import { fmt1, fmt2, fmtPct } from "@/lib/format";
import { periodOrUndefined, usePeriodParam, useSearchParamState } from "@/state/useSearchParamState";
import { useUiStore } from "@/state/uiStore";
import type { SriDimension } from "@/api/types";

export function EntityPage() {
  const { entityId = "" } = useParams();
  const [period] = usePeriodParam();
  const [dimension, setDimension] = useSearchParamState("dimension", "");
  const [capability] = useSearchParamState("capability", "");
  const [decision] = useSearchParamState("decision", "");
  const [status] = useSearchParamState("status", "");
  const [benchFeature] = useSearchParamState("metric", "note_template_score");
  const p = periodOrUndefined(period);
  const entity = useEntity(entityId, p);
  const findings = useFindings({
    period: p,
    entity_id: entityId,
    dimension: dimension || undefined,
    capability: capability || undefined,
    decision: decision || undefined,
    status: status || undefined,
    limit: 200,
  });
  const trend = useTrendEntity(entityId);
  const bench = useBenchmark(benchFeature || "note_template_score", p, entityId);
  const pushToast = useUiStore((s) => s.pushToast);

  const exportFile = async (kind: "pdf" | "csv") => {
    try {
      const blob = kind === "pdf" ? await endpoints.entityPdf(entityId, p) : await endpoints.csv("findings", p, entityId);
      download(blob, kind === "pdf" ? `SATSA_${entityId}_${period}.pdf` : `findings_${entityId}_${period}.csv`);
    } catch (e) {
      pushToast(e instanceof Error ? e.message : "Export failed", "error");
    }
  };

  return (
    <div className="space-y-4">
      <QueryBoundary query={entity} rows={10}>
        {(d) => (
          <>
            <header className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <nav className="text-xs text-muted">
                  <Link to={{ pathname: "/portfolio", search: `?period=${period}` }} className="hover:text-accent">
                    Portfolio
                  </Link>{" "}
                  / {d.entity.entity_id}
                </nav>
                <h1 className="text-3xl font-bold tracking-tight text-text drop-shadow-sm">{d.entity.name}</h1>
                <p className="text-sm text-muted font-medium mt-1 flex flex-wrap items-center gap-2">
                  <span className="px-2 py-0.5 rounded-full bg-surface border border-border shadow-sm">{d.entity.entity_id}</span>
                  <span className="px-2 py-0.5 rounded-full bg-surface border border-border shadow-sm">{d.entity.sector}</span>
                  <span className="px-2 py-0.5 rounded-full bg-surface border border-border shadow-sm">Size {d.entity.size_band}</span>
                  <span className="px-2 py-0.5 rounded-full bg-surface border border-border shadow-sm">Tier {d.entity.documented_soc_tier ?? "N/A"}</span>
                  <span className="px-2 py-0.5 rounded-full bg-surface border border-border shadow-sm">Period {d.period}</span>
                </p>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => exportFile("pdf")} {...guide("entity.export-pdf")}>Export PDF</Button>
                <Button onClick={() => exportFile("csv")} {...guide("entity.export-csv")}>Export findings CSV</Button>
              </div>
            </header>

            <div className="grid gap-3 lg:grid-cols-3">
              <Card
                className="lg:col-span-2"
                title={
                  d.sri ? (
                    <div className="flex items-baseline gap-2">
                      <h2 className="text-base font-semibold text-muted">Supervisory Risk Indicator</h2>
                      <span className="tabular text-4xl font-extrabold tracking-tighter text-text drop-shadow-sm">{fmt1(d.sri.sri)}</span>
                      <RiskBadge band={d.sri.band} />
                      <span className="text-xs text-muted">confidence {fmt2(d.sri.confidence)}</span>
                    </div>
                  ) : (
                    "Supervisory Risk Indicator"
                  )
                }
                actions={d.sri ? <Link to="/config" className="text-xs text-accent hover:underline" {...guide("entity.weights-link")}>weights {d.sri.weights_hash.slice(0, 8)} · edit</Link> : null}
              >
                {d.sri ? (
                  <table className="w-full text-sm" data-guide="entity.sri-table">
                    <caption className="sr-only">SRI dimension scores, weights and contributions</caption>
                    <thead>
                      <tr>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Dimension</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Score</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Weight</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Contribution</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Drivers</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.sri.dimensions.map((dim, di) => (
                        <tr
                          key={dim.name}
                          data-guide={di === 0 ? "entity.sri-row" : undefined}
                          className={dimension === dim.name ? "bg-accent-bg" : "hover:bg-surface"}
                          onClick={() => setDimension(dimension === dim.name ? undefined : dim.name)}
                          tabIndex={0}
                          onKeyDown={(e) => e.key === "Enter" && setDimension(dimension === dim.name ? undefined : dim.name)}
                        >
                          <td className="cursor-pointer px-2 py-1.5">{dim.label}</td>
                          <td className="px-2 py-1.5">
                            <span className="flex items-center gap-2">
                              <span className="tabular w-8">{fmt1(dim.score)}</span>
                              <ScoreBar score={dim.score} title={`${dim.label}: ${fmt1(dim.score)} of 100`} />
                            </span>
                          </td>
                          <td className="tabular px-2 py-1.5">{dim.weight.toFixed(2)}</td>
                          <td className="tabular px-2 py-1.5">{fmt1(dim.contribution)}</td>
                          <td className="px-2 py-1.5 text-xs text-muted">
                            {dim.subs.length
                              ? dim.subs.slice(0, 3).map((s) => (
                                  <span key={s.name} className="mr-2 whitespace-nowrap">
                                    {s.name} {s.percentile != null ? `${Math.round(s.percentile * 100)}th pct` : "n/a"}
                                    <SupportBadge support={s.support} />
                                  </span>
                                ))
                              : "module probability"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr>
                        <td className="px-2 py-1.5 font-medium">Total</td>
                        <td colSpan={2} />
                        <td className="tabular px-2 py-1.5 font-medium">{fmt1(d.sri.sri)}</td>
                        <td className="px-2 py-1.5 text-xs text-muted">sum of weight × dimension score · config <HashChip hash={d.sri.config_hash} label="config" /></td>
                      </tr>
                    </tfoot>
                  </table>
                ) : (
                  <p className="text-sm text-muted">This entity has not been scored for the selected period.</p>
                )}
              </Card>

              <div className="space-y-3">
                <Card title="Peer position" data-guide="entity.peer-chart">
                  <FilterBar>
                    <FilterSelect
                      label="Metric"
                      param="metric"
                      guide="shared.metric"
                      fallback="note_template_score"
                      options={d.headline_features.map((f) => ({ value: f.name, label: f.label }))}
                    />
                  </FilterBar>
                  <div className="mt-2">
                    <QueryBoundary query={bench} rows={3}>
                      {(b) => <PeerDistributionChart data={b} entityId={entityId} />}
                    </QueryBoundary>
                  </div>
                </Card>
                <Card title="Data quality" data-guide="entity.data-quality">
                  {d.data_quality ? (
                    <ul className="space-y-1 text-sm">
                      <li>Rows submitted: <span className="tabular">{d.data_quality.rows}</span></li>
                      <li>Validation errors: <span className="tabular">{fmtPct(d.data_quality.val_err_rate, 1)}</span></li>
                      <li>Validation warnings: <span className="tabular">{fmtPct(d.data_quality.val_warn_rate, 1)}</span></li>
                      {d.data_quality.fatal && <li className="text-risk-high">Submission rejected as unreadable</li>}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted">No submission for this period.</p>
                  )}
                </Card>
              </div>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <Card title="Supervisory Risk Indicator over time" data-guide="entity.trend">
                <QueryBoundary query={trend} rows={4}>
                  {(t) => (
                    <TrendChart
                      periods={t.periods}
                      series={[{ key: "sri", label: "SRI", values: t.sri }]}
                      caption={`SRI for ${entityId} across ${t.periods.length} submission periods.`}
                      height={160}
                      yLabel="SRI"
                    />
                  )}
                </QueryBoundary>
              </Card>
              <Card title="Key metrics against peers" data-guide="entity.headline-metrics">
                <table className="w-full text-sm">
                  <caption className="sr-only">Headline features compared with the peer group</caption>
                  <thead>
                    <tr>
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Metric</th>
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Value</th>
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Peer median</th>
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Position</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.headline_features.slice(0, 10).map((f) => (
                      <tr key={f.name} className="border-b border-border">
                        <td className="px-2 py-1.5">
                          {f.label}
                          <SupportBadge support={f.support} />
                        </td>
                        <td className="tabular px-2 py-1.5">{fmt2(f.value)}</td>
                        <td className="tabular px-2 py-1.5 text-muted">{fmt2(f.peer_median)}</td>
                        <td className="px-2 py-1.5">
                          <BulletBar value={f.value} median={f.peer_median} p10={f.p10} p90={f.p90} higherIsWorse={f.higher_is_worse} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </div>

            {d.controls.length > 0 && (
              <Card title="Control priorities" data-guide="entity.controls" actions={<span className="text-xs text-muted">Expected cost of missing the weaknesses behind each control</span>}>
                <ul className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                  {d.controls.map((c) => (
                    <li key={c.control_id} className="rounded-sm border border-border p-2 text-sm">
                      <div className="font-medium">{c.label}</div>
                      <div className="text-xs text-muted">
                        priority {fmt2(c.priority)} · {c.n_findings} finding{c.n_findings === 1 ? "" : "s"}
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            <Card
              title={`Findings${dimension ? ` · ${DIMENSION_LABELS[dimension as SriDimension] ?? dimension}` : capability ? ` · ${capability}` : ""}`}
              actions={
                <FilterBar>
                  <FilterSelect label="Dimension" param="dimension" guide="shared.dimension" options={Object.entries(DIMENSION_LABELS).map(([value, label]) => ({ value, label }))} />
                  <FilterSelect label="Decision" param="decision" guide="shared.decision" options={[{ value: "AUTO_FLAG", label: "Flagged" }, { value: "MANUAL_REVIEW", label: "Uncertain" }, { value: "AUTO_CLEAR", label: "Cleared" }]} />
                  <FilterSelect label="Status" param="status" guide="shared.status" options={[{ value: "open", label: "Open" }, { value: "reviewed", label: "Reviewed" }, { value: "uncertain", label: "Uncertain" }]} />
                </FilterBar>
              }
            >
              <QueryBoundary query={findings} rows={5}>
                {(f) => <FindingsTable items={f.items} period={period} tableGuide="entity.findings" firstRowGuide="entity.findings-first-row" emptyHint="Try clearing the dimension or status filter." />}
              </QueryBoundary>
            </Card>
          </>
        )}
      </QueryBoundary>
    </div>
  );
}
