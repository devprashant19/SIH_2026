import { useState } from "react";
import { Link } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { useControls, useFindings, useQueue, useQueueItem } from "@/api/hooks";
import { DataTable } from "@/components/data/DataTable";
import { FilterBar, FilterSelect } from "@/components/data/FilterBar";
import { EntityPicker, SectorPicker } from "@/components/data/Pickers";
import { FeedbackBar } from "@/components/domain/FeedbackBar";
import { FindingsTable } from "@/components/domain/FindingsTable";
import { DecisionBadge, FeedbackBadge, RiskBadge } from "@/components/domain/badges";
import { Button, Card, Drawer, QueryBoundary } from "@/components/ui/primitives";
import { fmt2, fmtMinutes, fmtProb } from "@/lib/format";
import { periodOrUndefined, usePeriodParam, useSearchParamState } from "@/state/useSearchParamState";
import type { QueueItem } from "@/api/types";

type Scope = "sample" | "entity" | "control";

export function QueuePage() {
  const [period] = usePeriodParam();
  const [scope, setScope] = useSearchParamState("scope", "sample");
  const [entity] = useSearchParamState("entity", "");
  const [sector] = useSearchParamState("sector", "");
  const [decision] = useSearchParamState("decision", "");
  const [selected, setSelected] = useState<QueueItem | null>(null);
  const p = periodOrUndefined(period);
  const queue = useQueue({ period: p, entity_id: entity || undefined, sector: sector || undefined, decision: decision || undefined, limit: 500 });
  const findings = useFindings({ period: p, entity_id: entity || undefined, sector: sector || undefined, decision: decision || undefined, status: "open", limit: 500 }, { enabled: scope === "entity" });
  const controls = useControls(p, sector || undefined);
  const detail = useQueueItem(selected?.flag_id);

  const columns: ColumnDef<QueueItem, any>[] = [
    { accessorKey: "queue_rank", header: "#", cell: (c) => <span className="tabular text-muted">{c.getValue<number>()}</span> },
    { accessorKey: "entity_id", header: "Entity", cell: (c) => <span className="font-medium">{c.getValue<string>()}</span> },
    { accessorKey: "alert_id", header: "Alert", cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span> },
    { id: "severity", header: "Severity", accessorFn: (r) => r.alert.severity, cell: (c) => <RiskBadge band={(c.getValue<string>() === "CRITICAL" ? "CRITICAL" : c.getValue<string>() === "HIGH" ? "HIGH" : c.getValue<string>() === "MEDIUM" ? "ELEVATED" : "LOW") as any} compact /> },
    { id: "category", header: "Category", accessorFn: (r) => r.alert.category },
    { id: "ttc", header: "Time to close", accessorFn: (r) => r.alert.time_to_close_min, cell: (c) => <span className="tabular">{fmtMinutes(c.getValue<number>())}</span> },
    { id: "rules", header: "Rules", accessorFn: (r) => r.rule_ids.join(", ") || "model", cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span> },
    { accessorKey: "p_alert", header: "p", cell: (c) => <span className="tabular">{fmtProb(c.getValue<number>())}</span> },
    { accessorKey: "decision", header: "Decision", cell: (c) => <DecisionBadge decision={c.getValue<any>()} p={c.row.original.p_alert} /> },
    { accessorKey: "feedback_status", header: "Review", cell: (c) => <FeedbackBadge status={c.getValue<string>()} /> },
  ];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Review queue</h1>
          <p className="text-sm text-muted">Prioritised work for manual examination. Uncertain items come first because the tool cannot decide them.</p>
        </div>
        <FilterBar>
          {(["sample", "entity", "control"] as Scope[]).map((s) => (
            <Button key={s} variant={(scope || "sample") === s ? "primary" : "default"} onClick={() => setScope(s)}>
              {s === "sample" ? "Alert samples" : s === "entity" ? "Entity findings" : "Controls and processes"}
            </Button>
          ))}
        </FilterBar>
      </header>

      <FilterBar>
        <EntityPicker />
        <SectorPicker />
        <FilterSelect label="Decision" param="decision" options={[{ value: "MANUAL_REVIEW", label: "Uncertain" }, { value: "AUTO_FLAG", label: "Flagged" }]} />
      </FilterBar>

      {(scope || "sample") === "sample" && (
        <Card title={queue.data ? `${queue.data.total} alert samples` : "Alert samples"} actions={<span className="text-xs text-muted">Sampling is round-robin across rules so every kind of weakness is represented</span>}>
          <QueryBoundary query={queue} rows={8}>
            {(d) => (
              <DataTable
                data={d.items}
                columns={columns}
                rowKey={(r) => r.flag_id}
                onRowClick={(r) => setSelected(r)}
                isRowActive={(r) => r.flag_id === selected?.flag_id}
                emptyTitle="Queue is clear for these filters"
                caption="Click a row to preview the alert and record a decision."
              />
            )}
          </QueryBoundary>
        </Card>
      )}

      {scope === "entity" && (
        <Card title="Entity findings awaiting review">
          <QueryBoundary query={findings} rows={8}>
            {(d) => <FindingsTable items={d.items} period={period} showEntity />}
          </QueryBoundary>
        </Card>
      )}

      {scope === "control" && (
        <Card title="Controls and processes by supervisory priority" actions={<span className="text-xs text-muted">Sum of expected cost of the findings attributed to each control</span>}>
          <QueryBoundary query={controls} rows={6}>
            {(rows) => (
              <table className="w-full text-sm">
                <caption className="sr-only">Control priorities</caption>
                <thead>
                  <tr>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Control</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Scope</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Priority</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Findings</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Top rules</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c, i) => (
                    <tr key={`${c.control_id}-${c.entity_id ?? "all"}-${i}`} className="border-b border-border">
                      <td className="px-2 py-1.5">{c.label}</td>
                      <td className="px-2 py-1.5">{c.entity_id ? <Link className="text-accent hover:underline" to={{ pathname: `/entities/${c.entity_id}`, search: `?period=${period}` }}>{c.entity_id}</Link> : <span className="text-muted">portfolio</span>}</td>
                      <td className="tabular px-2 py-1.5">{fmt2(c.priority)}</td>
                      <td className="tabular px-2 py-1.5">{c.n_findings}</td>
                      <td className="px-2 py-1.5 font-mono text-xs text-muted">{c.top_rule_ids.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </QueryBoundary>
        </Card>
      )}

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected ? `${selected.entity_id} · alert ${selected.alert_id}` : ""}>
        <QueryBoundary query={detail} rows={6}>
          {(d) => (
            <div className="space-y-3 text-sm">
              <p>{d.flag.rationale}</p>
              <p className="text-xs text-muted">{d.flag.queue_reason}</p>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                <dt className="text-muted">Severity</dt><dd>{d.alert.alert.severity}</dd>
                <dt className="text-muted">Category</dt><dd>{d.alert.alert.category}</dd>
                <dt className="text-muted">Asset</dt><dd>{d.alert.alert.asset_id ?? "—"}</dd>
                <dt className="text-muted">Time to close</dt><dd>{fmtMinutes(d.alert.alert.time_to_close_min)}</dd>
                <dt className="text-muted">Escalated</dt><dd>{d.alert.alert.escalation_flag ? "yes" : "no"}</dd>
                <dt className="text-muted">Closure reason</dt><dd>{d.alert.alert.closure_reason ?? "—"}</dd>
              </dl>
              {d.alert.alert.investigation_notes && (
                <div>
                  <p className="text-xs text-muted">Investigation note</p>
                  <p className="mt-1 rounded-sm bg-surface p-2 text-xs">{d.alert.alert.investigation_notes}</p>
                </div>
              )}
              {d.related_alerts.length > 0 && (
                <div>
                  <p className="text-xs text-muted">Alerts closed with an identical note</p>
                  <ul className="mt-1 space-y-0.5 font-mono text-xs">
                    {d.related_alerts.map((r) => <li key={r.alert_id}>{r.alert_id}</li>)}
                  </ul>
                </div>
              )}
              <FeedbackBar targetType="alert_flag" targetId={d.flag.flag_id} compact />
            </div>
          )}
        </QueryBoundary>
      </Drawer>
    </div>
  );
}
