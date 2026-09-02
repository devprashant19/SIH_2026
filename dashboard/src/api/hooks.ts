import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { endpoints, type FindingFilters } from "./endpoints";
import { qk } from "./queryKeys";
import type { FeedbackRequest } from "./types";

const stable = { staleTime: 60_000 };

export const useHealth = () => useQuery({ queryKey: qk.health(), queryFn: endpoints.health, ...stable });
export const usePeriods = () => useQuery({ queryKey: qk.periods(), queryFn: endpoints.periods, ...stable });
export const useSummary = (period?: string) => useQuery({ queryKey: qk.summary(period), queryFn: () => endpoints.summary(period) });

export const useEntities = () => useQuery({ queryKey: qk.entities(), queryFn: endpoints.entities, ...stable });
export const useHeatmap = (period?: string, lens = "sri", sector?: string) =>
  useQuery({ queryKey: qk.heatmap(period, lens, sector), queryFn: () => endpoints.heatmap(period, lens, sector) });
export const useEntity = (id: string, period?: string) =>
  useQuery({ queryKey: qk.entity(id, period), queryFn: () => endpoints.entity(id, period), enabled: !!id });
export const useEntitySri = (id: string, period?: string) =>
  useQuery({ queryKey: qk.entitySri(id, period), queryFn: () => endpoints.entitySri(id, period), enabled: !!id });

export const useFindings = (filters: FindingFilters, options?: Partial<UseQueryOptions<any>>) =>
  useQuery({ queryKey: qk.findings(filters), queryFn: () => endpoints.findings(filters), ...options });
export const useFinding = (id: string) =>
  useQuery({ queryKey: qk.finding(id), queryFn: () => endpoints.finding(id), enabled: !!id });
export const useEvidence = (id: string, limit: number, offset: number, sort?: string) =>
  useQuery({ queryKey: [...qk.evidence(id, offset), limit, sort], queryFn: () => endpoints.evidence(id, limit, offset, sort), enabled: !!id });
export const useAlert = (entity?: string, period?: string, alertId?: string) =>
  useQuery({ queryKey: qk.alert(entity ?? "", period ?? "", alertId ?? ""), queryFn: () => endpoints.alert(entity!, period!, alertId!), enabled: !!(entity && period && alertId) });

export const useQueue = (params: Parameters<typeof endpoints.queue>[0]) =>
  useQuery({ queryKey: qk.queue(params), queryFn: () => endpoints.queue(params) });
export const useQueueItem = (flagId?: string) =>
  useQuery({ queryKey: qk.queueItem(flagId ?? ""), queryFn: () => endpoints.queueItem(flagId!), enabled: !!flagId });
export const useControls = (period?: string, sector?: string, entityId?: string) =>
  useQuery({ queryKey: [...qk.controls(period, sector), entityId], queryFn: () => endpoints.controls(period, sector, entityId) });

export const useBenchmarkMetrics = () => useQuery({ queryKey: qk.benchmarkMetrics(), queryFn: endpoints.benchmarkMetrics, ...stable });
export const useBenchmark = (feature: string, period?: string, entityId?: string, group?: string) =>
  useQuery({ queryKey: qk.benchmark(feature, period, group, entityId), queryFn: () => endpoints.benchmark(feature, period, entityId, group), enabled: !!feature });
export const useBenchmarkRank = (period?: string, sector?: string) =>
  useQuery({ queryKey: qk.benchmarkRank(period, sector), queryFn: () => endpoints.benchmarkRank(period, sector) });

export const useCoverage = (period?: string, dimension = "category", sector?: string) =>
  useQuery({ queryKey: qk.coverage(period, sector, dimension), queryFn: () => endpoints.coverage(period, dimension, sector) });
export const useCoverageCell = (entity?: string, column?: string, period?: string, dimension = "category") =>
  useQuery({ queryKey: [...qk.coverageCell(entity ?? "", column ?? "", period), dimension], queryFn: () => endpoints.coverageCell(entity!, column!, period, dimension), enabled: !!(entity && column) });

export const useTrendEntity = (id: string, start?: string, end?: string) =>
  useQuery({ queryKey: qk.trendEntity(id, start, end), queryFn: () => endpoints.trendEntity(id, start, end), enabled: !!id });
export const useTrendSector = (sector?: string, start?: string, end?: string) =>
  useQuery({ queryKey: qk.trendSector(sector, start, end), queryFn: () => endpoints.trendSector(sector, start, end) });
export const useTrendControls = () => useQuery({ queryKey: qk.trendControls(), queryFn: () => endpoints.trendControls() });

export const useSubmissions = (period?: string, entityId?: string) =>
  useQuery({ queryKey: qk.submissions(period, entityId), queryFn: () => endpoints.submissions(period, entityId) });
export const useSubmission = (id?: string) =>
  useQuery({ queryKey: qk.submission(id ?? ""), queryFn: () => endpoints.submission(id!), enabled: !!id });

/** Polls while a pipeline or training job is running so the ingestion screen stays live. */
export const usePipelineStatus = (enabled = true) =>
  useQuery({
    queryKey: qk.pipelineStatus(),
    queryFn: endpoints.pipelineStatus,
    enabled,
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
  });

export const useConfig = () => useQuery({ queryKey: qk.config(), queryFn: endpoints.config });
export const useConfigHistory = () => useQuery({ queryKey: qk.configHistory(), queryFn: endpoints.configHistory });
export const useAuditRuns = (type?: string, period?: string) =>
  useQuery({ queryKey: qk.audit({ type, period }), queryFn: () => endpoints.auditRuns(type, period) });
export const useAuditRun = (id?: string) =>
  useQuery({ queryKey: qk.auditRun(id ?? ""), queryFn: () => endpoints.auditRun(id!), enabled: !!id });
export const useAuditVerify = () => useQuery({ queryKey: ["audit", "verify"], queryFn: endpoints.auditVerify, enabled: false });
export const useModels = () => useQuery({ queryKey: qk.models(), queryFn: endpoints.models });
export const useReports = () => useQuery({ queryKey: qk.reports(), queryFn: endpoints.reports });
export const useFeedbackStats = () => useQuery({ queryKey: qk.feedbackStats(), queryFn: endpoints.feedbackStats });

/** Feedback invalidates everything that shows a decision or a count. */
export function useFeedbackMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FeedbackRequest) => endpoints.postFeedback(body),
    onSuccess: (_data, body) => {
      qc.invalidateQueries({ queryKey: ["finding", body.target_id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      qc.invalidateQueries({ queryKey: ["feedback"] });
    },
  });
}

export function useBulkFeedbackMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (items: FeedbackRequest[]) => endpoints.postFeedbackBulk(items),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
    },
  });
}

export function useRunPipelineMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ period, force }: { period: string; force?: boolean }) => endpoints.runPipeline(period, force ?? false),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline"] }),
  });
}

export function useSaveConfigMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => endpoints.saveConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
      qc.invalidateQueries({ queryKey: ["health"] });
    },
  });
}

export function useWhatIfMutation() {
  return useMutation({ mutationFn: (body: Record<string, unknown>) => endpoints.whatIf(body) });
}

export function useUploadMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entityId, period, files }: { entityId: string; period: string; files: File[] }) =>
      endpoints.upload(entityId, period, files),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["submissions"] });
      qc.invalidateQueries({ queryKey: ["periods"] });
    },
  });
}
