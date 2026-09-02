import { useState } from "react";
import { useAuditRun, useAuditRuns, useModels } from "@/api/hooks";
import { endpoints } from "@/api/endpoints";
import { Button, Card, Drawer, HashChip, QueryBoundary } from "@/components/ui/primitives";
import { fmtDateTime, fmtInt } from "@/lib/format";
import { useSearchParamState } from "@/state/useSearchParamState";
import { useUiStore } from "@/state/uiStore";

const TYPES = ["PIPELINE", "INGEST", "FEEDBACK", "CONFIG", "TRAIN", "RECALIBRATE", "REPORT"];

export function AuditPage() {
  const [type, setType] = useSearchParamState("type", "");
  const [openRun, setOpenRun] = useState<string | null>(null);
  const runs = useAuditRuns(type || undefined);
  const detail = useAuditRun(openRun ?? undefined);
  const models = useModels();
  const pushToast = useUiStore((s) => s.pushToast);
  const [verified, setVerified] = useState<string | null>(null);

  const verify = async () => {
    try {
      const v = await endpoints.auditVerify();
      const msg = v.ok ? `Hash chain intact across ${v.n_runs} runs.` : `Chain broken at ${v.first_broken_run_id}: ${v.detail}`;
      setVerified(msg);
      pushToast(msg, v.ok ? "info" : "error");
    } catch (e) {
      pushToast(e instanceof Error ? e.message : "Verification failed", "error");
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Audit log</h1>
          <p className="text-sm text-muted">Every run is appended, never edited, and chained by hash so any later change is detectable.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant={type ? "default" : "primary"} onClick={() => setType(undefined)}>All</Button>
          {TYPES.map((t) => (
            <Button key={t} variant={type === t ? "primary" : "default"} onClick={() => setType(t)}>
              {t.toLowerCase()}
            </Button>
          ))}
          <Button onClick={verify}>Verify chain</Button>
        </div>
      </header>

      {verified && <p className="rounded-sm border border-border bg-surface px-3 py-2 text-sm">{verified}</p>}

      <Card title="Runs">
        <QueryBoundary query={runs} rows={8}>
          {(rows) => (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Audit runs</caption>
                <thead>
                  <tr>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Started</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Type</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Period</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Status</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">By</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Code</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Config</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Models</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Run hash</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.run_id} className="cursor-pointer border-b border-border hover:bg-surface" onClick={() => setOpenRun(r.run_id)}>
                      <td className="whitespace-nowrap px-2 py-1.5">{fmtDateTime(r.started_at)}</td>
                      <td className="px-2 py-1.5">{r.run_type.toLowerCase()}</td>
                      <td className="px-2 py-1.5">{r.submission_period ?? "—"}</td>
                      <td className={`px-2 py-1.5 ${r.status === "FAILED" ? "text-risk-high" : ""}`}>{r.status.replace("_", " ").toLowerCase()}</td>
                      <td className="px-2 py-1.5 text-muted">{r.triggered_by ?? "—"}</td>
                      <td className="px-2 py-1.5"><HashChip hash={r.code_hash} label="code" /></td>
                      <td className="px-2 py-1.5"><HashChip hash={r.config_hash} label="config" /></td>
                      <td className="px-2 py-1.5 text-xs text-muted">{Object.values(r.model_versions ?? {})[0] ?? "—"}</td>
                      <td className="px-2 py-1.5"><HashChip hash={r.run_hash} label="run" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryBoundary>
      </Card>

      <Card title="Model registry" actions={<span className="text-xs text-muted">Active models are pinned to the feature list they were trained on</span>}>
        <QueryBoundary query={models} rows={4}>
          {(rows) => (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Registered models</caption>
                <thead>
                  <tr>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Model</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Version</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Active</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Trained</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Rows</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Periods</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Metrics</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Artifact</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((m) => (
                    <tr key={`${m.model_name}-${m.version}`} className="border-b border-border">
                      <td className="px-2 py-1.5 font-medium">{m.model_name}</td>
                      <td className="px-2 py-1.5 font-mono text-xs">{m.version}</td>
                      <td className="px-2 py-1.5">{m.is_active ? "yes" : ""}</td>
                      <td className="px-2 py-1.5">{fmtDateTime(m.trained_at)}</td>
                      <td className="tabular px-2 py-1.5">{fmtInt(m.training_rows)}</td>
                      <td className="px-2 py-1.5 text-xs text-muted">{(m.training_periods ?? []).join(", ") || "feedback"}</td>
                      <td className="px-2 py-1.5 text-xs text-muted">
                        {Object.entries(m.metrics ?? {})
                          .filter(([k]) => ["ece", "brier", "calibrated", "n_labels", "n_rows"].includes(k))
                          .map(([k, v]) => `${k} ${typeof v === "number" ? v.toFixed(3) : String(v)}`)
                          .join(" · ")}
                      </td>
                      <td className="px-2 py-1.5"><HashChip hash={m.artifact_hash} label="artifact" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryBoundary>
      </Card>

      <Drawer open={!!openRun} onClose={() => setOpenRun(null)} title={`Run ${openRun ?? ""}`} width="max-w-3xl">
        <QueryBoundary query={detail} rows={6}>
          {(d) => (
            <div className="space-y-3 text-sm">
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                <dt className="text-muted">Type</dt><dd>{d.run_type}</dd>
                <dt className="text-muted">Status</dt><dd>{d.status}</dd>
                <dt className="text-muted">Period</dt><dd>{d.submission_period ?? "—"}</dd>
                <dt className="text-muted">Triggered by</dt><dd>{d.triggered_by} ({d.trigger_source})</dd>
                <dt className="text-muted">Started</dt><dd>{fmtDateTime(d.started_at)}</dd>
                <dt className="text-muted">Finished</dt><dd>{fmtDateTime(d.finished_at)}</dd>
                <dt className="text-muted">Rules version</dt><dd>{d.rules_version ?? "—"}</dd>
                <dt className="text-muted">Feature version</dt><dd>{(d as any).feature_version ?? "—"}</dd>
                <dt className="text-muted">Input hash</dt><dd><HashChip hash={d.input_hash} /></dd>
                <dt className="text-muted">Output hash</dt><dd><HashChip hash={d.output_hash} /></dd>
                <dt className="text-muted">Previous run hash</dt><dd><HashChip hash={d.prev_run_hash} /></dd>
                <dt className="text-muted">Run hash</dt><dd><HashChip hash={d.run_hash} /></dd>
              </dl>
              {d.error_text && <p className="rounded-sm border border-risk-high bg-risk-high-bg p-2 text-risk-high">{d.error_text}</p>}
              {d.stages?.length > 0 && (
                <div>
                  <p className="text-xs text-muted">Stages</p>
                  <table className="mt-1 w-full text-xs">
                    <thead>
                      <tr>
                        <th scope="col" className="border-b border-border px-1 py-1 text-left">Stage</th>
                        <th scope="col" className="border-b border-border px-1 py-1 text-left">Status</th>
                        <th scope="col" className="border-b border-border px-1 py-1 text-left">Rows</th>
                        <th scope="col" className="border-b border-border px-1 py-1 text-left">Seconds</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.stages.map((s) => (
                        <tr key={s.stage} className="border-b border-border">
                          <td className="px-1 py-1">{s.stage}</td>
                          <td className="px-1 py-1">{s.status}</td>
                          <td className="tabular px-1 py-1">{s.rows ?? "—"}</td>
                          <td className="tabular px-1 py-1">{s.seconds ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <details>
                <summary className="cursor-pointer text-xs text-muted">Configuration snapshot used by this run</summary>
                <pre className="mt-1 max-h-80 overflow-auto rounded-sm bg-surface p-2 text-xs">{JSON.stringify((d as any).config_snapshot, null, 1)}</pre>
              </details>
              <details>
                <summary className="cursor-pointer text-xs text-muted">Input manifest</summary>
                <pre className="mt-1 max-h-64 overflow-auto rounded-sm bg-surface p-2 text-xs">{JSON.stringify((d as any).input_manifest, null, 1)}</pre>
              </details>
            </div>
          )}
        </QueryBoundary>
      </Drawer>
    </div>
  );
}
