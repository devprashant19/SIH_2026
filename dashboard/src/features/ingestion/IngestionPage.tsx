import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { usePeriods, usePipelineStatus, useRunPipelineMutation, useSubmissions, useUploadMutation, useEntities } from "@/api/hooks";
import { FilterBar } from "@/components/data/FilterBar";
import { PeriodPicker } from "@/components/data/Pickers";
import { Button, Card, HashChip, QueryBoundary, Select } from "@/components/ui/primitives";
import { guide } from "@/guide/model";
import { fmtDateTime, fmtInt, fmtPct } from "@/lib/format";
import { periodOrUndefined, usePeriodParam } from "@/state/useSearchParamState";
import { useUiStore } from "@/state/uiStore";

export function IngestionPage() {
  const [period] = usePeriodParam();
  const p = periodOrUndefined(period);
  const entities = useEntities();
  const periods = usePeriods();
  const submissions = useSubmissions(p);
  const status = usePipelineStatus();
  const upload = useUploadMutation();
  const runPipeline = useRunPipelineMutation();
  const pushToast = useUiStore((s) => s.pushToast);
  const [entityId, setEntityId] = useState("");
  const [uploadPeriod, setUploadPeriod] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);

  const submit = () => {
    if (!entityId || !uploadPeriod || !files.length) {
      pushToast("Choose an entity, a period and at least one file.", "error");
      return;
    }
    upload.mutate(
      { entityId, period: uploadPeriod, files },
      {
        onSuccess: (r) => {
          pushToast(`${r.status.replace("_", " ").toLowerCase()}: ${Object.entries(r.tables ?? {}).map(([k, v]) => `${v} ${k}`).join(", ") || "no new rows"}`);
          setFiles([]);
        },
        onError: (e) => pushToast(e instanceof Error ? e.message : "Upload failed", "error"),
      },
    );
  };

  const run = () => {
    const target = p ?? periods.data?.[periods.data.length - 1]?.period;
    if (!target) {
      pushToast("Select a period to analyse.", "error");
      return;
    }
    runPipeline.mutate(
      { period: target },
      { onSuccess: () => pushToast(`Analysis started for ${target}`), onError: (e) => pushToast(e instanceof Error ? e.message : "Could not start the run", "error") },
    );
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Ingestion and data quality</h1>
          <p className="text-sm text-muted">Batch submissions from Critical Sector Entities. Validation results are supervisory evidence in their own right.</p>
        </div>
        <FilterBar>
          <PeriodPicker />
          <Button variant="primary" onClick={run} disabled={runPipeline.isPending || !!status.data?.running} {...guide("ingestion.run")}>
            {status.data?.running ? "Analysis running…" : "Run analysis"}
          </Button>
        </FilterBar>
      </header>

      <div className="grid gap-3 lg:grid-cols-3">
        <Card title="Upload a submission" className="lg:col-span-1">
          <div className="space-y-2 text-sm">
            <label className="block">
              <span className="text-muted">Entity</span>
              <QueryBoundary query={entities} rows={1}>
                {(list) => (
                  <Select className="mt-1 w-full" value={entityId} onChange={(e) => setEntityId(e.target.value)} {...guide("ingestion.upload-entity")}>
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
              <span className="text-muted">Submission period</span>
              <input className="mt-1 w-full rounded-sm border border-border bg-bg px-2 py-1" placeholder="2026-07" value={uploadPeriod} onChange={(e) => setUploadPeriod(e.target.value)} {...guide("ingestion.upload-period")} />
            </label>
            <label className="block">
              <span className="text-muted">Files (CSV, JSON or SQLite)</span>
              <input className="mt-1 w-full text-xs" type="file" multiple onChange={(e) => setFiles(Array.from(e.target.files ?? []))} {...guide("ingestion.upload-files")} />
            </label>
            {files.length > 0 && <p className="text-xs text-muted">{files.map((f) => f.name).join(", ")}</p>}
            <Button variant="primary" onClick={submit} disabled={upload.isPending} {...guide("ingestion.upload-submit")}>
              {upload.isPending ? "Uploading…" : "Upload and validate"}
            </Button>
          </div>
        </Card>

        <Card title="Analysis status" className="lg:col-span-2" data-guide="ingestion.status">
          {status.data?.running ? (
            <div className="space-y-1 text-sm">
              <p className="font-medium">Running {status.data.running.kind.toLowerCase()} for {String(status.data.running.params.period ?? "")}</p>
              <p className="text-xs text-muted">Started {fmtDateTime(status.data.running.started_at)}</p>
            </div>
          ) : status.data?.last_run ? (
            <div className="space-y-1 text-sm">
              <p>
                Last run <span className="font-medium">{status.data.last_run.status.replace("_", " ").toLowerCase()}</span> for {status.data.last_run.submission_period},
                finished {fmtDateTime(status.data.last_run.finished_at)}
              </p>
              <p className="text-xs text-muted">
                code <HashChip hash={status.data.last_run.code_hash} label="code" /> config <HashChip hash={status.data.last_run.config_hash} label="config" /> models{" "}
                {Object.entries(status.data.last_run.model_versions ?? {}).map(([k, v]) => `${k} ${v}`).join(", ") || "none"}
              </p>
              <table className="mt-2 w-full text-xs">
                <caption className="sr-only">Pipeline stages of the last run</caption>
                <thead>
                  <tr>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Stage</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Status</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Rows</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Seconds</th>
                  </tr>
                </thead>
                <tbody>
                  {status.data.last_run.stages.map((s) => (
                    <tr key={s.stage} className="border-b border-border">
                      <td className="px-2 py-1">{s.stage.replace(/_/g, " ").toLowerCase()}</td>
                      <td className="px-2 py-1">{s.status}</td>
                      <td className="tabular px-2 py-1">{s.rows ?? "—"}</td>
                      <td className="tabular px-2 py-1">{s.seconds ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Link to="/audit" className="text-xs text-accent hover:underline">
                Open the audit log
              </Link>
            </div>
          ) : (
            <p className="text-sm text-muted">No analysis has been run yet.</p>
          )}
        </Card>
      </div>

      <Card title="Submissions and validation results" actions={<span className="text-xs text-muted">A CSE that cannot submit clean data is itself a supervisory signal</span>}>
        <QueryBoundary query={submissions} rows={6}>
          {(list) => (
            <table className="w-full text-sm" data-guide="ingestion.submissions">
              <caption className="sr-only">Submissions with validation counts</caption>
              <thead>
                <tr>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Entity</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Period</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Format</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Rows</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Accepted</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Rejected</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Errors</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Warnings</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Received</th>
                </tr>
              </thead>
              <tbody>
                {list.map((s) => {
                  const lc = s.validation?.level_counts ?? {};
                  const rows = s.validation?.n_rows || 1;
                  const open = expanded === s.submission_id;
                  return (
                    <Fragment key={s.submission_id}>
                      <tr className="cursor-pointer border-b border-border hover:bg-surface" onClick={() => setExpanded(open ? null : s.submission_id)}>
                        <td className="px-2 py-1.5 font-medium">{s.entity_id}</td>
                        <td className="px-2 py-1.5">{s.submission_period}</td>
                        <td className="px-2 py-1.5">{s.source_format}</td>
                        <td className="tabular px-2 py-1.5">{fmtInt(s.row_count)}</td>
                        <td className="tabular px-2 py-1.5">{fmtInt(s.accepted_rows)}</td>
                        <td className="tabular px-2 py-1.5">{fmtInt(s.rejected_rows)}</td>
                        <td className="tabular px-2 py-1.5">{fmtPct((lc.ERROR ?? 0) / rows, 1)}</td>
                        <td className="tabular px-2 py-1.5">{fmtPct((lc.WARN ?? 0) / rows, 1)}</td>
                        <td className="px-2 py-1.5 text-xs text-muted">{fmtDateTime(s.received_at)}</td>
                      </tr>
                      {open && s.validation && (
                        <tr>
                          <td colSpan={9} className="bg-surface px-3 py-2 text-xs">
                            <p className="font-medium">Validation checks triggered</p>
                            <ul className="mt-1 grid gap-1 md:grid-cols-3">
                              {Object.entries(s.validation.counts).map(([check, n]) => (
                                <li key={check}>
                                  <span className="font-mono">{check}</span>: {n} row{n === 1 ? "" : "s"}
                                  {s.validation!.samples?.[check]?.length ? <span className="text-muted"> (rows {s.validation!.samples[check].slice(0, 5).join(", ")})</span> : null}
                                </li>
                              ))}
                            </ul>
                            {s.validation.unmapped_columns.length > 0 && (
                              <p className="mt-1">Unmapped source columns: <span className="font-mono">{s.validation.unmapped_columns.join(", ")}</span></p>
                            )}
                            <p className="mt-1 text-muted">File {s.file_name} · sha256 {s.file_hash.slice(0, 16)}</p>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          )}
        </QueryBoundary>
      </Card>
    </div>
  );
}
