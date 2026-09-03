import { useState } from "react";
import { Link } from "react-router-dom";
import { useCoverage, useCoverageCell } from "@/api/hooks";
import { FilterBar } from "@/components/data/FilterBar";
import { SectorPicker } from "@/components/data/Pickers";
import { Button, Card, QueryBoundary } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { guide } from "@/guide/model";
import { fmt1 } from "@/lib/format";
import { periodOrUndefined, usePeriodParam, useSearchParamState } from "@/state/useSearchParamState";
import type { CoverageStatus } from "@/api/types";

const CELL: Record<CoverageStatus, { cls: string; text: string; title: string }> = {
  present: { cls: "bg-risk-low-bg text-risk-low", text: "ok", title: "reported at the expected level" },
  low: { cls: "bg-risk-elevated-bg text-risk-elevated", text: "low", title: "reported, but below the peer 10th percentile" },
  absent: { cls: "hatch-absent text-risk-high font-medium", text: "ABS", title: "expected but entirely absent" },
  na: { cls: "bg-surface text-muted", text: "–", title: "not expected for this entity" },
};

export function CoveragePage() {
  const [period] = usePeriodParam();
  const [dimension, setDimension] = useSearchParamState("dimension", "category");
  const [sector] = useSearchParamState("sector", "");
  const [cell, setCell] = useState<{ entity: string; column: string } | null>(null);
  const p = periodOrUndefined(period);
  const dim = dimension || "category";
  const coverage = useCoverage(p, dim, sector || undefined);
  const detail = useCoverageCell(cell?.entity, cell?.column, p, dim);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Negative space</h1>
          <p className="text-sm text-muted">Evidence a supervisor would expect to see and does not. Absent cells are hatched and labelled, never colour alone.</p>
        </div>
        {/* Written out rather than mapped so each button carries a literal guide anchor. */}
        <FilterBar>
          <Button variant={dim === "category" ? "primary" : "default"} onClick={() => setDimension("category")} {...guide("coverage.dimension-category")}>
            Alert categories
          </Button>
          <Button variant={dim === "asset_class" ? "primary" : "default"} onClick={() => setDimension("asset_class")} {...guide("coverage.dimension-asset")}>
            Asset classes
          </Button>
          <Button variant={dim === "source" ? "primary" : "default"} onClick={() => setDimension("source")} {...guide("coverage.dimension-source")}>
            Telemetry sources
          </Button>
          <SectorPicker />
        </FilterBar>
      </header>

      <div className="flex flex-wrap items-center gap-3 text-xs" {...guide("coverage.legend")}>
        {(Object.keys(CELL) as CoverageStatus[]).map((s) => (
          <span key={s} className="inline-flex items-center gap-1">
            <span className={cn("inline-block rounded-sm px-1.5 py-0.5", CELL[s].cls)}>{CELL[s].text}</span>
            <span className="text-muted">{CELL[s].title}</span>
          </span>
        ))}
      </div>

      <Card title="Coverage matrix">
        <QueryBoundary query={coverage} rows={8}>
          {(m) =>
            m.rows.length ? (
              <div className="overflow-x-auto" {...guide("coverage.matrix")}>
                <table className="w-full text-sm">
                  <caption className="sr-only">Coverage of expected {m.dimension} per entity for {m.period}</caption>
                  <thead>
                    <tr>
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Entity</th>
                      {m.columns.map((c) => (
                        <th key={c} scope="col" className="border-b border-border px-1 py-1 text-left text-xs">
                          {c.replace(/_/g, " ")}
                        </th>
                      ))}
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Absent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.rows.map((r, ri) => (
                      <tr key={r.entity_id} className="border-b border-border">
                        <th scope="row" className="whitespace-nowrap px-2 py-1 text-left font-normal">
                          <Link to={{ pathname: `/entities/${r.entity_id}`, search: `?period=${period}` }} className="text-accent hover:underline">
                            {r.entity_id}
                          </Link>
                          <div className="text-xs text-muted">{r.sector}</div>
                        </th>
                        {r.cells.map((c, i) => (
                          <td key={m.columns[i]} className="px-0.5 py-0.5">
                            <button
                              type="button"
                              data-guide={ri === 0 && i === 0 ? "coverage.matrix-cell" : undefined}
                              onClick={() => setCell({ entity: r.entity_id, column: m.columns[i] })}
                              title={`${r.entity_id} · ${m.columns[i]}: ${CELL[c.status].title}${c.count != null ? ` (${fmt1(c.count)} observed, peer median ${fmt1(c.peer_median)})` : ""}`}
                              className={cn("w-full rounded-sm px-1.5 py-1 text-center text-xs", CELL[c.status].cls)}
                            >
                              {CELL[c.status].text}
                            </button>
                          </td>
                        ))}
                        <td className="tabular px-2 py-1 text-center">{r.cells.filter((c) => c.status === "absent").length}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th scope="row" className="px-2 py-1 text-left text-xs font-normal text-muted">Absent across entities</th>
                      {m.columns.map((c, i) => (
                        <td key={c} className="tabular px-1 py-1 text-center text-xs text-muted">
                          {m.rows.filter((r) => r.cells[i].status === "absent").length}
                        </td>
                      ))}
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted">No coverage data for this period.</p>
            )
          }
        </QueryBoundary>
      </Card>

      {cell && (
        <Card title={`${cell.entity} · ${cell.column.replace(/_/g, " ")}`} actions={<Button variant="ghost" onClick={() => setCell(null)}>Close</Button>}>
          <QueryBoundary query={detail} rows={3}>
            {(d) => (
              <div className="space-y-2 text-sm">
                <p>
                  Status: <span className="font-medium">{CELL[d.status].title}</span>. Observed {fmt1(d.observed)}
                  {d.peer_median != null && `, peer median ${fmt1(d.peer_median)}`}.
                </p>
                <p className="text-muted">Expected because {d.expected_reason}.</p>
                {d.finding_id && (
                  <Link to={{ pathname: `/findings/${d.finding_id}`, search: `?period=${period}` }} className="inline-block text-accent hover:underline">
                    Open the related finding
                  </Link>
                )}
              </div>
            )}
          </QueryBoundary>
        </Card>
      )}
    </div>
  );
}
