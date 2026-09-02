/**
 * API contract shared with satsa/api/schemas.py. Keep the two in sync; field names are
 * snake_case exactly as the FastAPI responses emit them.
 */

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
export type RiskBand = "CRITICAL" | "HIGH" | "ELEVATED" | "LOW";
export type Decision = "AUTO_FLAG" | "MANUAL_REVIEW" | "AUTO_CLEAR";
export type FindingSource = "RULE" | "ML" | "COMBINED";
export type FindingClass = "execution_gap" | "negative_space";
export type FeedbackDecision = "ACCEPT" | "REJECT" | "DEFER";
export type SupportFlag = "OK" | "LOW_N" | "DEGENERATE" | "MISSING";
export type RunStatus = "RUNNING" | "SUCCESS" | "FAILED" | "SKIPPED_IDENTICAL";
export type RunType = "PIPELINE" | "INGEST" | "FEEDBACK" | "TRAIN" | "REPORT" | "RECALIBRATE" | "CONFIG";

export type SriDimension =
  | "execution_gap"
  | "negative_space"
  | "escalation_discipline"
  | "investigation_quality"
  | "data_integrity"
  | "trend_penalty";

export type Capability =
  | "Threat Detection"
  | "Investigation"
  | "Escalation"
  | "Incident Response"
  | "Security Operations"
  | "Governance and Oversight"
  | "Operational Discipline"
  | "Cyber Resilience";

// ---- meta ---------------------------------------------------------------------------

export interface Health {
  status: "ok";
  app_version: string;
  code_hash: string;
  config_hash: string;
  db_path: string;
  active_models: Record<string, string>;
}

export interface PeriodInfo {
  period: string;
  n_entities: number;
  n_submissions: number;
  latest_run_id: string | null;
  status: RunStatus | null;
}

export interface Summary {
  period: string | null;
  run_id: string | null;
  n_entities: number;
  n_high_risk: number;
  high_risk_delta: number | null;
  n_open_findings: number;
  n_uncertain: number;
  n_dq_failures: number;
}

// ---- entities -----------------------------------------------------------------------

export interface Entity {
  entity_id: string;
  name: string;
  sector: string;
  size_band: "S" | "M" | "L" | "XL";
  documented_soc_tier: number | null;
  documented_asset_count: number | null;
  peer_group_id: string | null;
}

export interface HeatmapRow {
  entity_id: string;
  name: string;
  sector: string;
  size_band: string;
  sri: number | null;
  band: RiskBand | null;
  confidence: number | null;
  priority_rank: number | null;
  dims: Partial<Record<SriDimension, number>>;
  capabilities: Partial<Record<Capability, number>>;
  n_findings: number;
  n_manual_review: number;
  uncertain: boolean;
  trend: number[];
}

export interface Heatmap {
  period: string;
  run_id: string | null;
  lens: "sri" | "capability";
  rows: HeatmapRow[];
}

export interface SriSubIndicator {
  name: string;
  raw: number | null;
  percentile: number | null;
  higher_is_worse: boolean;
  weight: number;
  effective_weight: number;
  contribution: number;
  support: SupportFlag;
  peer_median: number | null;
}

export interface SriDimensionScore {
  name: SriDimension;
  label: string;
  weight: number;
  score: number;
  contribution: number;
  capabilities: Capability[];
  subs: SriSubIndicator[];
}

export interface SriScorecard {
  entity_id: string;
  period: string;
  run_id: string;
  sri: number;
  band: RiskBand;
  confidence: number;
  weights_hash: string;
  config_hash: string;
  sri_delta_prev: number | null;
  dimensions: SriDimensionScore[];
}

export interface HeadlineFeature {
  name: string;
  label: string;
  value: number | null;
  peer_median: number | null;
  p10: number | null;
  p90: number | null;
  z: number | null;
  percentile: number | null;
  support: SupportFlag;
  higher_is_worse: boolean;
}

export interface EntityDetail {
  entity: Entity;
  period: string;
  run_id: string | null;
  sri: SriScorecard | null;
  findings_summary: { by_class: Record<FindingClass, number>; by_decision: Record<Decision, number> };
  headline_features: HeadlineFeature[];
  controls: EntityControl[];
  recent_periods: { period: string; sri: number | null }[];
  data_quality: { rows: number; val_err_rate: number; val_warn_rate: number; fatal: boolean } | null;
}

// ---- findings -----------------------------------------------------------------------

export interface FindingListItem {
  finding_id: string;
  entity_id: string;
  entity_name: string;
  period: string;
  module: "A" | "B";
  finding_class: FindingClass;
  source: FindingSource;
  rule_id: string | null;
  control_id: string | null;
  capability: Capability | null;
  dimension: SriDimension;
  title: string;
  severity: RiskBand;
  p_final: number;
  decision: Decision;
  priority_rank: number | null;
  feedback_status: FeedbackDecision | null;
}

export interface Paginated<T> {
  total: number;
  items: T[];
  limit: number;
  offset: number;
}

export interface EvidenceFeature {
  name: string;
  label: string;
  value: number | null;
  peer_median: number | null;
  p10: number | null;
  p90: number | null;
  z: number | null;
  higher_is_worse: boolean;
}

export interface ShapContribution {
  feature: string;
  label?: string;
  value: number | null;
  shap: number;
  peer_median: number | null;
}

export interface RuleEvidence {
  rule_id: string;
  version: string;
  name: string;
  template: string;
  params: Record<string, unknown>;
  evaluated: Record<string, unknown>;
}

export interface FindingDetail extends FindingListItem {
  rule_version: string | null;
  scope: "entity" | "asset";
  asset_id: string | null;
  p_rule: number | null;
  p_ml: number | null;
  calibrated: boolean;
  t_star: number;
  band_low: number;
  band_high: number;
  expected_cost: number;
  rationale: string;
  what_would_change: string | null;
  score_components: Record<string, unknown>;
  evidence_features: EvidenceFeature[];
  shap: { method: string; base_value: number; output: number; contributions: ShapContribution[] } | null;
  rule: RuleEvidence | null;
  n_evidence_alerts: number;
  feedback: FeedbackRecord[];
  created_at: string;
}

export interface AlertRecord {
  alert_id: string;
  entity_id: string;
  submission_period: string;
  submission_id: string | null;
  raw_row_index: number | null;
  ts: string | null;
  severity: Severity | null;
  category: string | null;
  asset_id: string | null;
  source_system: string | null;
  analyst_id: string | null;
  analyst_action: string | null;
  acknowledged_at: string | null;
  investigated_at: string | null;
  closed_at: string | null;
  time_to_close_min: number | null;
  escalation_flag: boolean;
  escalated_at: string | null;
  closure_reason: string | null;
  investigation_notes: string | null;
  root_cause_flag: boolean | null;
  remediation_ticket_id: string | null;
  rule_name: string | null;
  validation_flags: string[];
}

export interface AlertWithSource {
  alert: AlertRecord;
  raw_line: string | null;
  submission: { file_name: string; file_hash: string } | null;
  flags: { flag_id: string; rule_ids: string[]; p_alert: number; decision: Decision }[];
}

// ---- review queue -------------------------------------------------------------------

export interface QueueItem {
  flag_id: string;
  entity_id: string;
  entity_name: string;
  period: string;
  alert_id: string;
  rule_ids: string[];
  flag_source: "RULE" | "ML" | "BOTH";
  p_alert: number;
  decision: Decision;
  queue_rank: number;
  queue_reason: string;
  rationale: string;
  alert: Pick<
    AlertRecord,
    "severity" | "category" | "asset_id" | "time_to_close_min" | "analyst_action" | "closure_reason"
  > & { notes_excerpt: string | null };
  feedback_status: FeedbackDecision | null;
}

export interface ControlPriority {
  control_id: string;
  label: string;
  entity_id: string | null;
  priority: number;
  n_findings: number;
  top_rule_ids: string[];
}

export interface EntityControl {
  control_id: string;
  label: string;
  priority: number;
  n_findings: number;
  top_rule_ids?: string[];
}

// ---- feedback -----------------------------------------------------------------------

export interface FeedbackRecord {
  feedback_id: string;
  target_type: "finding" | "alert_flag";
  target_id: string;
  decision: FeedbackDecision;
  reviewer_id: string;
  note: string | null;
  p_at_decision: number | null;
  created_at: string;
}

export interface FeedbackRequest {
  target_type: "finding" | "alert_flag";
  target_id: string;
  decision: FeedbackDecision;
  reviewer_id: string;
  note?: string;
}

export interface FeedbackStats {
  rules: { rule_id: string; n: number; accept_rate: number | null }[];
  calibrators: { name: string; version: string; n_labels: number; ece: number | null; calibrated: boolean }[];
  n_feedback: number;
  n_targets: number;
}

// ---- benchmarking / negative space / trends ---------------------------------------

export interface MetricInfo {
  key: string;
  label: string;
  unit: string | null;
  higher_is_worse: boolean;
  group: string;
  formula: string;
  headline: boolean;
}

export interface Benchmark {
  feature: string;
  label: string;
  unit: string | null;
  higher_is_worse: boolean;
  period: string;
  peer_group_id: string;
  peer_level: number;
  stats: { n: number; median: number | null; mad: number | null; p10: number | null; p90: number | null };
  entities: { entity_id: string; name: string; value: number | null; z: number | null; percentile: number | null }[];
  entity_value: number | null;
}

export type CoverageStatus = "present" | "low" | "absent" | "na";

export interface CoverageCell {
  status: CoverageStatus;
  count: number | null;
  peer_median: number | null;
  finding_id: string | null;
}

export interface CoverageMatrix {
  period: string | null;
  dimension: "category" | "asset_class" | "source";
  columns: string[];
  rows: { entity_id: string; name: string; sector: string; cells: CoverageCell[] }[];
}

export interface CoverageCellDetail {
  entity_id: string;
  column: string;
  status: CoverageStatus;
  observed: number;
  expected_reason: string;
  peer_share_reporting: number | null;
  peer_median: number | null;
  finding_id: string | null;
}

export interface TrendSeries {
  periods: string[];
  sri: (number | null)[];
  dims: Record<SriDimension, (number | null)[]>;
  features: Record<string, (number | null)[]>;
  findings_count: { A: number[]; B: number[] };
}

export interface SectorTrend {
  periods: string[];
  median_sri: (number | null)[];
  p25: (number | null)[];
  p75: (number | null)[];
  entities: Record<string, (number | null)[]>;
}

// ---- ingestion / pipeline ---------------------------------------------------------

export interface ValidationReport {
  fatal: boolean;
  n_rows: number;
  n_accepted: number;
  n_rejected: number;
  counts: Record<string, number>;
  samples: Record<string, number[]>;
  unmapped_columns: string[];
  messages: string[];
  level_counts: Record<string, number>;
}

export interface Submission {
  submission_id: string;
  entity_id: string;
  submission_period: string;
  source_format: string;
  file_name: string;
  file_hash: string;
  received_at: string;
  row_count: number;
  accepted_rows: number;
  rejected_rows: number;
  fatal: boolean;
  superseded: boolean;
  validation: ValidationReport | null;
}

export interface PipelineRun {
  run_id: string;
  run_type: RunType;
  submission_period: string | null;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  config_hash: string | null;
  code_hash: string | null;
  rules_version: string | null;
  model_versions: Record<string, string>;
  stages: { stage: string; status: string; rows: number | null; seconds: number | null; error: string | null }[];
  error_text: string | null;
  input_hash: string | null;
  output_hash: string | null;
  run_hash: string | null;
}

// ---- config / audit / models ------------------------------------------------------

export interface AppConfig {
  config_hash: string;
  weights_hash: string;
  sri_weights: {
    dimensions: Record<string, { weight: number; label?: string; subs?: Record<string, number>; capabilities?: Capability[]; source?: string }>;
    bands?: Record<string, [number, number]>;
  };
  costs: {
    band_halfwidth: number;
    classes: Record<string, { C_FP: number; C_FN: number; band_halfwidth?: number }>;
    derived: Record<string, { t_star: number; band_halfwidth: number }>;
  };
  rules: Record<string, {
    rule_id: string; version: string; name: string; scope: string; control_id: string;
    capability: Capability; prior_weight: number; enabled: boolean; params: Record<string, unknown>;
  }>;
  controls: Record<string, string>;
  rules_version: string;
  pipeline: Record<string, unknown>;
  features: Record<string, unknown>;
}

export interface WhatIfResult {
  period: string;
  n_uncertain_before: number;
  n_uncertain_after: number;
  rows: { entity_id: string; name: string; sri_current: number | null; sri_what_if: number | null }[];
}

export interface AuditRun extends PipelineRun {
  triggered_by: string | null;
  trigger_source: string | null;
  app_version: string | null;
  config_snapshot: Record<string, unknown> | null;
  prev_run_hash: string | null;
}

export interface AuditVerify {
  ok: boolean;
  n_runs: number;
  first_broken_run_id: string | null;
  detail: string | null;
}

export interface ModelVersion {
  model_name: string;
  version: string;
  is_active: boolean;
  trained_at: string | null;
  training_periods: string[];
  training_rows: number | null;
  feature_list_hash: string | null;
  metrics: Record<string, number | null>;
  hyperparams: Record<string, unknown>;
  parent_version: string | null;
  artifact_hash: string | null;
}

export interface ReportRecord {
  report_id: string;
  scope: "entity" | "period";
  target: string;
  period: string;
  format: "pdf" | "csv";
  created_at: string;
  config_hash: string;
  run_id: string | null;
  file_name: string;
}


// ---- additions used by endpoints.ts -----------------------------------------------

export interface Job {
  job_id: string;
  kind: string;
  status: "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED";
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, any>;
  error: string | null;
  params: Record<string, any>;
}

export interface RankTable {
  period: string;
  features: { key: string; label: string; higher_is_worse: boolean }[];
  rows: {
    entity_id: string;
    name: string;
    sector: string;
    sri: number | null;
    band: RiskBand | null;
    values: Record<string, number | null>;
    percentiles: Record<string, number | null>;
  }[];
}

export interface TrendControls {
  periods: string[];
  controls: { control_id: string; label: string; series: number[]; n_findings: number[] }[];
}
