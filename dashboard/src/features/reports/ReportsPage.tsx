import { useState } from "react";
import { useEntities, useFeedbackStats, usePeriods, useReports } from "@/api/hooks";
import { download, endpoints } from "@/api/endpoints";
import { Button, Card, QueryBoundary, Select } from "@/components/ui/primitives";
import { guide } from "@/guide/model";
import { fmt2, fmtDateTime } from "@/lib/format";
import { periodOrUndefined, usePeriodParam } from "@/state/useSearchParamState";
import { useUiStore } from "@/state/uiStore";

export function ReportsPage() {
  const [period] = usePeriodParam();
  const p = periodOrUndefined(period);
  const entities = useEntities();
  const periods = usePeriods();
  const reports = useReports();
  const stats = useFeedbackStats();
  const pushToast = useUiStore((s) => s.pushToast);
  const [entityId, setEntityId] = useState("");
  const [reportPeriod, setReportPeriod] = useState("");

  const target = reportPeriod || p || periods.data?.[periods.data.length - 1]?.period;

  const run = async (fn: () => Promise<Blob>, name: string) => {
    try {
      download(await fn(), name);
      reports.refetch();
    } catch (e) {
      pushToast(e instanceof Error ? e.message : "Report generation failed", "error");
    }
  };

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Reports</h1>
        <p className="text-sm text-muted">Every export records the code, configuration and model versions that produced it, so a finding can always be reproduced.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-2">
        <Card title="Entity report">
          <div className="space-y-2 text-sm">
            <label className="block">
              <span className="text-muted">Entity</span>
              <QueryBoundary query={entities} rows={1}>
                {(list) => (
                  <Select className="mt-1 w-full" value={entityId} onChange={(e) => setEntityId(e.target.value)} {...guide("reports.entity-select")}>
                    <option value="">Choose…</option>
                    {list.map((e) => (
                      <option key={e.entity_id} value={e.entity_id}>
                        {e.entity_id} · {e.name}
                      </option>
                    ))}
                  </Select>
                )}
              </QueryBoundary>
            </label>
            <label className="block">
              <span className="text-muted">Period</span>
              <Select className="mt-1 w-full" value={reportPeriod} onChange={(e) => setReportPeriod(e.target.value)}>
                <option value="">{p ?? "latest"}</option>
                {(periods.data ?? []).map((x) => (
                  <option key={x.period} value={x.period}>
                    {x.period}
                  </option>
                ))}
              </Select>
            </label>
            <p className="text-xs text-muted">Includes the SRI scorecard arithmetic, every finding with its rationale, the alert samples selected for review, and the feedback recorded so far.</p>
            <div className="flex gap-2">
              <Button variant="primary" disabled={!entityId} onClick={() => run(() => endpoints.entityPdf(entityId, target), `SATSA_${entityId}_${target}.pdf`)} {...guide("reports.entity-pdf")}>
                Generate PDF
              </Button>
              <Button disabled={!entityId} onClick={() => run(() => endpoints.csv("findings", target, entityId), `findings_${entityId}_${target}.csv`)} {...guide("reports.entity-csv")}>
                Findings CSV
              </Button>
            </div>
          </div>
        </Card>

        <Card title="Portfolio report">
          <div className="space-y-2 text-sm">
            <p className="text-muted">Period {target ?? "—"}</p>
            <p className="text-xs text-muted">Heatmap of every entity, control priorities across the portfolio, and the counts a supervisor needs for a period summary.</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" disabled={!target} onClick={() => run(() => endpoints.periodPdf(target!), `SATSA_portfolio_${target}.pdf`)} {...guide("reports.portfolio-pdf")}>
                Generate PDF
              </Button>
              {(["findings", "sri", "alert_samples", "features"] as const).map((kind, i) => (
                <Button key={kind} data-guide={i === 0 ? "reports.portfolio-csv" : undefined} disabled={!target} onClick={() => run(() => endpoints.csv(kind, target), `${kind}_${target}.csv`)}>
                  {kind.replace("_", " ")} CSV
                </Button>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <Card title="Feedback and calibration" data-guide="reports.feedback-stats" actions={<span className="text-xs text-muted">Supervisor decisions are what recalibrate the model</span>}>
        <QueryBoundary query={stats} rows={3}>
          {(s) => (
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <p className="text-sm">{s.n_feedback} decisions recorded on {s.n_targets} items.</p>
                <table className="mt-2 w-full text-sm">
                  <caption className="sr-only">Accept rate per rule</caption>
                  <thead>
                    <tr>
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Rule</th>
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Decisions</th>
                      <th scope="col" className="border-b border-border px-2 py-1 text-left">Accepted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.rules.map((r) => (
                      <tr key={r.rule_id} className="border-b border-border">
                        <td className="px-2 py-1.5 font-mono text-xs">{r.rule_id}</td>
                        <td className="tabular px-2 py-1.5">{r.n}</td>
                        <td className="tabular px-2 py-1.5">{r.accept_rate == null ? "—" : `${Math.round(r.accept_rate * 100)}%`}</td>
                      </tr>
                    ))}
                    {!s.rules.length && (
                      <tr>
                        <td colSpan={3} className="px-2 py-1.5 text-muted">No rule feedback yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div>
                <p className="text-sm font-medium">Calibrators</p>
                <ul className="mt-1 space-y-1 text-sm">
                  {s.calibrators.map((c) => (
                    <li key={c.name}>
                      {c.name} <span className="font-mono text-xs">{c.version}</span> · {c.n_labels} labels ·{" "}
                      {c.calibrated ? `expected calibration error ${fmt2(c.ece)}` : "uncalibrated, showing raw scores"}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </QueryBoundary>
      </Card>

      <Card title="Generated reports" data-guide="reports.history">
        <QueryBoundary query={reports} rows={3}>
          {(rows) =>
            rows.length ? (
              <table className="w-full text-sm">
                <caption className="sr-only">Report history</caption>
                <thead>
                  <tr>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Generated</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Scope</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Target</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Period</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Format</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">File</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 25).map((r) => (
                    <tr key={r.report_id} className="border-b border-border">
                      <td className="whitespace-nowrap px-2 py-1.5">{fmtDateTime(r.created_at)}</td>
                      <td className="px-2 py-1.5">{r.scope}</td>
                      <td className="px-2 py-1.5">{r.target}</td>
                      <td className="px-2 py-1.5">{r.period}</td>
                      <td className="px-2 py-1.5">{r.format}</td>
                      <td className="px-2 py-1.5 font-mono text-xs text-muted">{r.file_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-muted">No reports generated yet.</p>
            )
          }
        </QueryBoundary>
      </Card>
    </div>
  );
}
