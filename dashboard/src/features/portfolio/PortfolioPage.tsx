import { Link, useNavigate } from "react-router-dom";
import { useFindings, useHeatmap, useSummary } from "@/api/hooks";
import { RiskHeatmap } from "@/components/charts/RiskHeatmap";
import { FilterBar } from "@/components/data/FilterBar";
import { SectorPicker } from "@/components/data/Pickers";
import { FindingsTable } from "@/components/domain/FindingsTable";
import { StatTile } from "@/components/domain/StatTile";
import { Button, Card, QueryBoundary } from "@/components/ui/primitives";
import { guide } from "@/guide/model";
import { fmtInt } from "@/lib/format";
import { periodOrUndefined, usePeriodParam, useSearchParamState } from "@/state/useSearchParamState";

export function PortfolioPage() {
  const [period] = usePeriodParam();
  const [sector] = useSearchParamState("sector", "");
  const [lens, setLens] = useSearchParamState("lens", "sri");
  const p = periodOrUndefined(period);
  const navigate = useNavigate();
  const summary = useSummary(p);
  const heatmap = useHeatmap(p, lens || "sri", sector || undefined);
  const queue = useFindings({ period: p, status: "open", sort: "priority", limit: 10 });

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Portfolio overview</h1>
          <p className="text-sm text-muted">Entities requiring supervisory attention, ranked by expected cost of missing a weakness.</p>
        </div>
        <FilterBar>
          <SectorPicker />
          <span className="inline-flex items-center gap-1">
            <span className="text-muted">Lens</span>
            <Button variant={lens !== "capability" ? "primary" : "default"} onClick={() => setLens("sri")} {...guide("portfolio.lens-sri")}>
              Risk dimensions
            </Button>
            <Button variant={lens === "capability" ? "primary" : "default"} onClick={() => setLens("capability")} {...guide("portfolio.lens-capability")}>
              Capability areas
            </Button>
          </span>
        </FilterBar>
      </header>

      <QueryBoundary query={summary} rows={1}>
        {(s) => (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <StatTile label="Entities scored" value={fmtInt(s.n_entities)} hint={s.period ?? "no data"} data-guide="portfolio.tile-entities" />
            <StatTile label="High or critical" value={fmtInt(s.n_high_risk)} delta={s.high_risk_delta} tone="risk" data-guide="portfolio.tile-high-risk" />
            <StatTile label="Open findings" value={fmtInt(s.n_open_findings)} to={`/findings?period=${period}&status=open`} data-guide="portfolio.tile-open" />
            <StatTile label="Uncertain" value={fmtInt(s.n_uncertain)} tone="uncertain" hint="inside the decision band" to={`/findings?period=${period}&decision=MANUAL_REVIEW`} data-guide="portfolio.tile-uncertain" />
            <StatTile label="Data-quality failures" value={fmtInt(s.n_dq_failures)} to={`/ingestion?period=${period}`} data-guide="portfolio.tile-dq" />
          </div>
        )}
      </QueryBoundary>

      <Card title={lens === "capability" ? "Entity risk by capability area" : "Entity risk by supervisory dimension"} actions={<span className="text-xs text-muted">Ranked by supervisory priority: risk score, weighted by confidence and by how much the entity matters (sector and size). Click a cell to open that dimension.</span>}>
        <QueryBoundary query={heatmap} rows={8}>
          {(h) =>
            h.rows.length ? (
              <RiskHeatmap
                rows={h.rows}
                lens={h.lens}
                period={period}
                // Under the capability lens the column key is a capability name, not an SRI
                // dimension, so it has to go into a different parameter or the entity page
                // filters on a value that can never match.
                onCellClick={(entityId, key) =>
                  navigate({
                    pathname: `/entities/${entityId}`,
                    search: `?period=${period}&${h.lens === "capability" ? "capability" : "dimension"}=${encodeURIComponent(key)}`,
                  })
                }
              />
            ) : (
              <p className="text-sm text-muted">No scored entities for this period. Ingest submissions and run the pipeline from the ingestion screen.</p>
            )
          }
        </QueryBoundary>
      </Card>

      <Card title="Prioritised review queue" actions={<Link className="text-sm text-accent hover:underline" to={`/findings?period=${period}&status=open`} {...guide("portfolio.see-all-findings")}>See all findings</Link>}>
        <QueryBoundary query={queue} rows={6}>
          {(q) => <FindingsTable items={q.items} period={period} showEntity tableGuide="portfolio.queue-preview" emptyHint="Nothing awaiting review for this period." />}
        </QueryBoundary>
      </Card>
    </div>
  );
}
