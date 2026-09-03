import { useCallback, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAlert, useEvidence, useFinding } from "@/api/hooks";
import { ContributionBar, BulletBar, ThresholdLine } from "@/components/charts/primitives";
import { DataTable } from "@/components/data/DataTable";
import { FeedbackBar } from "@/components/domain/FeedbackBar";
import { DecisionBadge, RiskBadge, TypeBadge } from "@/components/domain/badges";
import { Button, Card, Drawer, QueryBoundary, Tabs } from "@/components/ui/primitives";
import { fmt2, fmtDateTime, fmtMinutes, fmtProb } from "@/lib/format";
import { usePeriodParam, useSearchParamState } from "@/state/useSearchParamState";
import type { AlertRecord, ShapContribution } from "@/api/types";
import type { ColumnDef } from "@tanstack/react-table";

const PAGE = 25;

export function FindingPage() {
  const { findingId = "" } = useParams();
  const [period] = usePeriodParam();
  const [tab, setTab] = useSearchParamState("tab", "evidence");
  const [offset, setOffset] = useState(0);
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null);
  const revealRow = useCallback((el: HTMLTableRowElement | null) => {
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, []);
  const [openAlert, setOpenAlert] = useState<AlertRecord | null>(null);
  const finding = useFinding(findingId);
  const evidence = useEvidence(findingId, PAGE, offset, "ttc");
  const alertDetail = useAlert(openAlert?.entity_id, openAlert?.submission_period, openAlert?.alert_id);

  const columns: ColumnDef<AlertRecord, any>[] = [
    { accessorKey: "alert_id", header: "Alert", cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span> },
    { accessorKey: "ts", header: "Raised", cell: (c) => fmtDateTime(c.getValue<string>()) },
    { accessorKey: "severity", header: "Severity" },
    { accessorKey: "category", header: "Category" },
    { accessorKey: "asset_id", header: "Asset" },
    { accessorKey: "time_to_close_min", header: "Time to close", cell: (c) => <span className="tabular">{fmtMinutes(c.getValue<number>())}</span> },
    { accessorKey: "escalation_flag", header: "Escalated", cell: (c) => (c.getValue<boolean>() ? "yes" : "no") },
    { accessorKey: "closure_reason", header: "Closure" },
    { accessorKey: "investigation_notes", header: "Investigation note", cell: (c) => <span className="line-clamp-2 text-xs text-muted">{c.getValue<string>() ?? "—"}</span> },
  ];

  return (
    <QueryBoundary query={finding} rows={10}>
      {(f) => {
        const shapScale = f.shap ? Math.max(...f.shap.contributions.map((c) => Math.abs(c.shap)), 0.01) : 1;
        return (
          <div className="space-y-4">
            <header className="space-y-2">
              <nav className="text-xs text-muted">
                <Link to={{ pathname: "/portfolio", search: `?period=${period}` }} className="hover:text-accent">Portfolio</Link>
                {" / "}
                <Link to={{ pathname: `/entities/${f.entity_id}`, search: `?period=${period}` }} className="hover:text-accent">{f.entity_id}</Link>
                {" / "}Finding
              </nav>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold">{f.title}</h1>
                <RiskBadge band={f.severity} />
                <TypeBadge source={f.source} />
                {f.rule_id && <span className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-xs">{f.rule_id} v{f.rule_version}</span>}
                {f.capability && <span className="rounded-sm border border-border px-1.5 py-0.5 text-xs text-muted">{f.capability}</span>}
                <DecisionBadge decision={f.decision} p={f.p_final} tStar={f.t_star} bandRange={[f.band_low, f.band_high]} />
              </div>
              <p className="max-w-4xl text-sm">{f.rationale}</p>
              <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
                <span>p = {fmtProb(f.p_final)}{f.p_rule != null && ` (rules ${fmtProb(f.p_rule)}`}{f.p_ml != null && `, model ${fmtProb(f.p_ml)}`}{f.p_rule != null && ")"}</span>
                <span title={f.p_ml == null ? "This finding comes from a deterministic rule, so there is no model probability to calibrate." : undefined}>
                  {f.p_ml == null
                    ? "rule score, no model involved"
                    : f.calibrated
                      ? "calibrated model probability"
                      : "uncalibrated model score — too few labelled decisions yet"}
                </span>
                <span>expected cost if missed: {fmt2(f.expected_cost)}</span>
                <span>{f.n_evidence_alerts} evidence alerts</span>
              </div>
              <div className="max-w-md">
                <ThresholdLine tStar={f.t_star} band={f.t_star - f.band_low} marks={[{ p: f.p_final, label: `p = ${fmtProb(f.p_final)}` }]} />
              </div>
            </header>

            <Card title="Supervisor decision">
              <FeedbackBar targetType="finding" targetId={f.finding_id} status={f.feedback_status} />
              {f.feedback.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs text-muted">
                  {f.feedback.map((h) => (
                    <li key={h.feedback_id}>
                      {fmtDateTime(h.created_at)} · {h.reviewer_id} · <span className="font-medium">{h.decision.toLowerCase()}</span>
                      {h.note ? ` — ${h.note}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Tabs
              active={tab || "evidence"}
              onChange={setTab}
              tabs={[
                { key: "evidence", label: "Evidence" },
                { key: "explanation", label: "Explanation" },
                { key: "records", label: `Raw records (${f.n_evidence_alerts})` },
              ]}
            />

            {(tab || "evidence") === "evidence" && (
              <Card title="Feature values against the peer group">
                {f.evidence_features.length ? (
                  <table className="w-full text-sm">
                    <caption className="sr-only">Evidence features with peer comparison</caption>
                    <thead>
                      <tr>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Feature</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Entity</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Peer median</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">p10–p90</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">z</th>
                        <th scope="col" className="border-b border-border px-2 py-1 text-left">Position</th>
                      </tr>
                    </thead>
                    <tbody>
                      {f.evidence_features.map((e) => (
                        <tr
                          key={e.name}
                          // The ref moves when the selection changes, so this fires exactly once
                          // per selection and brings the row into view after a jump from the
                          // model-attribution tab.
                          ref={selectedFeature === e.name ? revealRow : undefined}
                          tabIndex={0}
                          className={selectedFeature === e.name ? "bg-accent-bg" : "border-b border-border"}
                          onClick={() => setSelectedFeature(e.name)}
                          onKeyDown={(ev) => ev.key === "Enter" && setSelectedFeature(e.name)}
                        >
                          <td className="cursor-pointer px-2 py-1.5">{e.label}</td>
                          <td className="tabular px-2 py-1.5 font-medium">{fmt2(e.value)}</td>
                          <td className="tabular px-2 py-1.5 text-muted">{fmt2(e.peer_median)}</td>
                          <td className="tabular px-2 py-1.5 text-muted">{fmt2(e.p10)}–{fmt2(e.p90)}</td>
                          <td className="tabular px-2 py-1.5">{fmt2(e.z)}</td>
                          <td className="px-2 py-1.5"><BulletBar value={e.value} median={e.peer_median} p10={e.p10} p90={e.p90} higherIsWorse={e.higher_is_worse} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="text-sm text-muted">This finding is evidenced by the rule condition below rather than by peer-relative features.</p>
                )}
              </Card>
            )}

            {tab === "explanation" && (
              <div className="grid gap-3 lg:grid-cols-2">
                {f.rule && (
                  <Card title={`Rule ${f.rule.rule_id} · ${f.rule.name}`}>
                    <p className="text-xs text-muted">Template</p>
                    <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-sm bg-surface p-2 text-xs">{f.rule.template}</pre>
                    <p className="mt-2 text-xs text-muted">Parameters</p>
                    <pre className="mt-1 overflow-x-auto rounded-sm bg-surface p-2 text-xs">{JSON.stringify(f.rule.params, null, 1)}</pre>
                    <p className="mt-2 text-xs text-muted">Evaluated values</p>
                    <pre className="mt-1 max-h-64 overflow-auto rounded-sm bg-surface p-2 text-xs">{JSON.stringify(f.rule.evaluated, null, 1)}</pre>
                  </Card>
                )}
                {f.shap && (
                  <Card title="Model attribution" actions={<span className="text-xs text-muted">{f.shap.method === "shap_tree_isolation_forest" ? "SHAP on the isolation forest" : "peer z-score attribution"}</span>}>
                    <ul className="space-y-1.5">
                      {f.shap.contributions.map((c: ShapContribution & { label?: string }) => {
                        const inEvidence = f.evidence_features.some((e) => e.name === c.feature);
                        return (
                          <li key={c.feature}>
                            <button
                              type="button"
                              disabled={!inEvidence}
                              onClick={() => {
                                setSelectedFeature(c.feature);
                                setTab("evidence");
                              }}
                              title={inEvidence ? "Show this feature's value against the peer group" : "This feature has no peer comparison on this finding"}
                              className="grid w-full grid-cols-[minmax(140px,1fr)_80px_1fr] items-center gap-2 rounded-sm px-1 py-0.5 text-left text-sm enabled:hover:bg-accent-bg disabled:cursor-default"
                            >
                              <span className="truncate" title={c.feature}>{c.label ?? c.feature}</span>
                              <span className="tabular text-xs text-muted">{c.value == null ? "—" : fmt2(c.value)}</span>
                              <span className="flex items-center gap-2">
                                <ContributionBar value={c.shap} scale={shapScale} />
                                <span className="tabular w-12 text-right text-xs">{c.shap >= 0 ? "+" : ""}{fmt2(c.shap)}</span>
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                    {f.what_would_change && <p className="mt-3 text-sm text-muted">{f.what_would_change}</p>}
                  </Card>
                )}
                {!f.rule && !f.shap && <Card title="Explanation"><p className="text-sm text-muted">No attribution available for this finding.</p></Card>}
              </div>
            )}

            {tab === "records" && (
              <Card
                title="Underlying alert records"
                actions={
                  <span className="flex items-center gap-2 text-xs">
                    <Button onClick={() => setOffset(Math.max(0, offset - PAGE))} disabled={offset === 0}>Previous</Button>
                    <span className="text-muted">{offset + 1}–{Math.min(offset + PAGE, f.n_evidence_alerts)} of {f.n_evidence_alerts}</span>
                    <Button onClick={() => setOffset(offset + PAGE)} disabled={offset + PAGE >= f.n_evidence_alerts}>Next</Button>
                  </span>
                }
              >
                <QueryBoundary query={evidence} rows={6}>
                  {(e) => (
                    <DataTable
                      data={e.items}
                      columns={columns}
                      rowKey={(r) => r.alert_id}
                      onRowClick={(r) => setOpenAlert(r)}
                      emptyTitle="This finding has no alert-level evidence"
                      emptyHint="Entity-level findings are evidenced by the feature values and rule condition."
                      caption="Click a row to see the record as submitted."
                    />
                  )}
                </QueryBoundary>
              </Card>
            )}

            <Drawer open={!!openAlert} onClose={() => setOpenAlert(null)} title={`Alert ${openAlert?.alert_id ?? ""}`}>
              <QueryBoundary query={alertDetail} rows={6}>
                {(a) => (
                  <div className="space-y-3 text-sm">
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                      {Object.entries(a.alert).map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="text-muted">{k}</dt>
                          <dd className="break-words">{Array.isArray(v) ? v.join(", ") || "—" : String(v ?? "—")}</dd>
                        </div>
                      ))}
                    </dl>
                    {a.submission && (
                      <p className="text-xs text-muted">
                        Submitted in {a.submission.file_name} (sha256 {a.submission.file_hash.slice(0, 12)})
                      </p>
                    )}
                    {a.raw_line && (
                      <div>
                        <p className="text-xs text-muted">As submitted</p>
                        <pre className="mt-1 max-h-64 overflow-auto rounded-sm bg-surface p-2 text-xs">{a.raw_line}</pre>
                      </div>
                    )}
                  </div>
                )}
              </QueryBoundary>
            </Drawer>
          </div>
        );
      }}
    </QueryBoundary>
  );
}
