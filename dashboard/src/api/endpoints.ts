import { api, apiBlob } from "./client";
import type {
  AlertWithSource, AppConfig, AuditRun, AuditVerify, Benchmark, ControlPriority, CoverageCellDetail,
  CoverageMatrix, EntityDetail, Entity, FeedbackRecord, FeedbackRequest, FeedbackStats, FindingDetail,
  FindingListItem, Health, Heatmap, Job, MetricInfo, ModelVersion, Paginated, PeriodInfo, PipelineRun,
  QueueItem, RankTable, ReportRecord, SectorTrend, SriScorecard, Submission, Summary, TrendControls,
  TrendSeries, WhatIfResult, AlertRecord,
} from "./types";

export type FindingFilters = {
  period?: string; entity_id?: string; sector?: string; module?: string; decision?: string; rule_id?: string;
  control_id?: string; min_p?: number; dimension?: string; capability?: string; status?: string; sort?: string;
  limit?: number; offset?: number;
};

export const endpoints = {
  health: () => api<Health>("/health"),
  periods: () => api<PeriodInfo[]>("/periods"),
  summary: (period?: string) => api<Summary>("/summary", { params: { period } }),

  entities: () => api<Entity[]>("/entities"),
  heatmap: (period?: string, lens = "sri", sector?: string) =>
    api<Heatmap>("/entities/heatmap", { params: { period, lens, sector } }),
  entity: (id: string, period?: string) => api<EntityDetail>(`/entities/${id}`, { params: { period } }),
  entitySri: (id: string, period?: string) => api<SriScorecard>(`/entities/${id}/sri`, { params: { period } }),
  entityFeatures: (id: string, period?: string) =>
    api<{ period: string; features: Record<string, number | null>; peer_z: Record<string, number | null>; headline: EntityDetail["headline_features"] }>(
      `/entities/${id}/features`, { params: { period } }),

  findings: (f: FindingFilters) => api<Paginated<FindingListItem>>("/findings", { params: f }),
  finding: (id: string) => api<FindingDetail>(`/findings/${id}`),
  evidence: (id: string, limit = 25, offset = 0, sort?: string) =>
    api<Paginated<AlertRecord>>(`/findings/${id}/evidence`, { params: { limit, offset, sort } }),
  alert: (entity: string, period: string, alertId: string) =>
    api<AlertWithSource>(`/alerts/${entity}/${period}/${alertId}`),

  queue: (params: { period?: string; entity_id?: string; decision?: string; rule_id?: string; sector?: string; limit?: number; offset?: number }) =>
    api<Paginated<QueueItem>>("/review/queue", { params }),
  queueItem: (flagId: string) => api<{ flag: QueueItem & { evidence: unknown }; alert: AlertWithSource; related_alerts: AlertRecord[]; feedback: FeedbackRecord[] }>(`/review/queue/${flagId}`),
  controls: (period?: string, sector?: string, entity_id?: string) =>
    api<ControlPriority[]>("/controls/priority", { params: { period, sector, entity_id } }),

  postFeedback: (body: FeedbackRequest) => api<FeedbackRecord>("/feedback", { method: "POST", json: body }),
  postFeedbackBulk: (items: FeedbackRequest[]) =>
    api<{ recorded: number; items: FeedbackRecord[] }>("/feedback/bulk", { method: "POST", json: { items } }),
  feedbackFor: (targetId: string) => api<FeedbackRecord[]>("/feedback", { params: { target_id: targetId } }),
  feedbackStats: () => api<FeedbackStats>("/feedback/stats"),
  recalibrate: (promote: boolean) => api<Record<string, unknown>>("/feedback/recalibrate", { method: "POST", json: { promote } }),

  benchmarkMetrics: () => api<MetricInfo[]>("/benchmark/metrics"),
  benchmark: (feature: string, period?: string, entity_id?: string, peer_group?: string) =>
    api<Benchmark>("/benchmark", { params: { feature, period, entity_id, peer_group } }),
  benchmarkRank: (period?: string, sector?: string, features?: string) =>
    api<RankTable>("/benchmark/rank", { params: { period, sector, features } }),

  coverage: (period?: string, dimension = "category", sector?: string) =>
    api<CoverageMatrix>("/coverage", { params: { period, dimension, sector } }),
  coverageCell: (entity: string, column: string, period?: string, dimension = "category") =>
    api<CoverageCellDetail>(`/coverage/${entity}/${encodeURIComponent(column)}`, { params: { period, dimension } }),

  trendEntity: (id: string, start?: string, end?: string) => api<TrendSeries>(`/trends/entities/${id}`, { params: { start, end } }),
  trendSector: (sector?: string, start?: string, end?: string) => api<SectorTrend>("/trends/sector", { params: { sector, start, end } }),
  trendControls: (start?: string, end?: string) => api<TrendControls>("/trends/controls", { params: { start, end } }),

  submissions: (period?: string, entity_id?: string) => api<Submission[]>("/ingest/submissions", { params: { period, entity_id } }),
  submission: (id: string) => api<Submission>(`/ingest/submissions/${id}`),
  upload: (entityId: string, period: string, files: File[], mapping = "generic_csv") => {
    const fd = new FormData();
    fd.append("entity_id", entityId);
    fd.append("period", period);
    fd.append("mapping", mapping);
    files.forEach((f) => fd.append("files", f, f.name));
    return api<{ submission_id: string; status: string; tables: Record<string, number>; validation: Submission["validation"] }>(
      "/ingest/upload", { method: "POST", body: fd });
  },
  scan: () => api<{ ingested: string[]; skipped: string[]; errors: string[] }>("/ingest/scan", { method: "POST" }),

  runPipeline: (period: string, force = false) => api<Job>("/pipeline/run", { method: "POST", json: { period, force } }),
  job: (jobId: string) => api<Job>(`/pipeline/jobs/${jobId}`),
  pipelineStatus: () => api<{ running: Job | null; last_run: PipelineRun | null }>("/pipeline/status"),
  pipelineRuns: (period?: string) => api<PipelineRun[]>("/pipeline/runs", { params: { period } }),

  config: () => api<AppConfig>("/config"),
  saveConfig: (body: Record<string, unknown>) => api<AppConfig>("/config", { method: "PUT", json: body }),
  whatIf: (body: Record<string, unknown>) => api<WhatIfResult>("/config/what-if", { method: "POST", json: body }),
  configHistory: () => api<{ config_hash: string; saved_at: string; saved_by: string; note: string | null }[]>("/config/history"),

  auditRuns: (type?: string, period?: string, limit = 100) => api<AuditRun[]>("/audit/runs", { params: { type, period, limit } }),
  auditRun: (id: string) => api<AuditRun>(`/audit/runs/${id}`),
  auditVerify: () => api<AuditVerify>("/audit/verify"),
  models: () => api<ModelVersion[]>("/models"),
  train: (periods: string[], promote: boolean) => api<Job>("/models/train", { method: "POST", json: { periods, promote } }),

  reports: () => api<ReportRecord[]>("/reports"),
  entityPdf: (id: string, period?: string) => apiBlob(`/reports/entity/${id}.pdf`, { period }),
  periodPdf: (period: string) => apiBlob(`/reports/period/${period}.pdf`),
  csv: (kind: string, period?: string, entity_id?: string) => apiBlob(`/reports/${kind}.csv`, { period, entity_id }),
};

/** Trigger a browser download for a blob returned by one of the report endpoints. */
export function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
