-- SAT-SA analytics store. Applied by satsa.db.migrate.apply_schema (idempotent).
-- Every analytic table carries run_id; rows are never updated or deleted between runs.
-- "Current" results for a period = rows from the latest audit_runs row with status='SUCCESS'.

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL,
  applied_at TIMESTAMP DEFAULT current_timestamp
);

-- ---------------------------------------------------------------------------
-- Ingested data
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_submissions (
  submission_id     VARCHAR PRIMARY KEY,
  entity_id         VARCHAR NOT NULL,
  submission_period VARCHAR NOT NULL,          -- 'YYYY-MM'
  source_format     VARCHAR,                   -- csv | json | sqlite
  adapter           VARCHAR,
  mapping_name      VARCHAR,
  file_name         VARCHAR,
  file_path         VARCHAR,                   -- archived copy under data/processed/
  file_hash         VARCHAR NOT NULL,
  file_bytes        BIGINT,
  received_at       TIMESTAMP DEFAULT current_timestamp,
  row_count         INTEGER,
  accepted_rows     INTEGER,
  rejected_rows     INTEGER,
  validation_json   JSON,                      -- ValidationReport
  fatal             BOOLEAN DEFAULT FALSE,
  superseded        BOOLEAN DEFAULT FALSE,
  superseded_by     VARCHAR,
  ingest_run_id     VARCHAR
);

CREATE TABLE IF NOT EXISTS entities (
  entity_id              VARCHAR PRIMARY KEY,
  name                   VARCHAR,
  sector                 VARCHAR,
  size_band              VARCHAR,
  documented_soc_tier    INTEGER,
  documented_asset_count INTEGER,
  peer_group_id          VARCHAR,
  updated_at             TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS assets (
  asset_id                   VARCHAR NOT NULL,
  entity_id                  VARCHAR NOT NULL,
  criticality_tier           VARCHAR,
  asset_class                VARCHAR,
  expected_telemetry_sources VARCHAR[],
  hostname                   VARCHAR,
  first_seen_period          VARCHAR,
  updated_at                 TIMESTAMP DEFAULT current_timestamp,
  PRIMARY KEY (entity_id, asset_id)
);

CREATE TABLE IF NOT EXISTS alerts (
  alert_id              VARCHAR NOT NULL,
  entity_id             VARCHAR NOT NULL,
  submission_period     VARCHAR NOT NULL,
  submission_id         VARCHAR,
  raw_row_index         INTEGER,
  ts                    TIMESTAMP,
  severity              VARCHAR,
  category              VARCHAR,
  asset_id              VARCHAR,
  source_system         VARCHAR,
  analyst_id            VARCHAR,
  analyst_action        VARCHAR,
  acknowledged_at       TIMESTAMP,
  investigated_at       TIMESTAMP,
  closed_at             TIMESTAMP,
  time_to_close_min     DOUBLE,
  escalation_flag       BOOLEAN DEFAULT FALSE,
  escalated_at          TIMESTAMP,
  closure_reason        VARCHAR,
  investigation_notes   VARCHAR,
  root_cause_flag       BOOLEAN,
  remediation_ticket_id VARCHAR,
  rule_name             VARCHAR,
  validation_flags      VARCHAR[],             -- e.g. ['V-04','V-12']
  PRIMARY KEY (entity_id, submission_period, alert_id)
);
CREATE INDEX IF NOT EXISTS idx_alerts_ep ON alerts (entity_id, submission_period);
CREATE INDEX IF NOT EXISTS idx_alerts_asset ON alerts (entity_id, asset_id);

CREATE TABLE IF NOT EXISTS escalations (
  escalation_id         VARCHAR NOT NULL,
  entity_id             VARCHAR NOT NULL,
  alert_id              VARCHAR,
  submission_period     VARCHAR,
  raised_at             TIMESTAMP,
  acknowledged_by_ir_at TIMESTAMP,
  incident_id           VARCHAR,
  outcome               VARCHAR,
  PRIMARY KEY (entity_id, escalation_id)
);

CREATE TABLE IF NOT EXISTS incidents (
  incident_id       VARCHAR NOT NULL,
  entity_id         VARCHAR NOT NULL,
  submission_period VARCHAR,
  opened_at         TIMESTAMP,
  closed_at         TIMESTAMP,
  severity          VARCHAR,
  root_cause        VARCHAR,
  linked_alert_ids  VARCHAR[],
  PRIMARY KEY (entity_id, incident_id)
);

-- ---------------------------------------------------------------------------
-- Derived analytics (all keyed by run_id)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS features_entity_period (
  entity_id          VARCHAR NOT NULL,
  submission_period  VARCHAR NOT NULL,
  run_id             VARCHAR NOT NULL,
  feature_version    VARCHAR,
  computed_at        TIMESTAMP DEFAULT current_timestamp,
  -- headline columns for SQL convenience; the full vector is in features_json
  n_alerts                            INTEGER,
  n_alerts_critical                   INTEGER,
  n_alerts_high                       INTEGER,
  n_closed                            INTEGER,
  ttc_median_critical                 DOUBLE,
  ttc_median_high                     DOUBLE,
  ttc_cv_critical                     DOUBLE,
  fast_close_rate_critical            DOUBLE,
  fast_close_rate_high                DOUBLE,
  ack_only_rate                       DOUBLE,
  ack_then_close_no_invest_rate       DOUBLE,
  escalation_ratio                    DOUBLE,
  escalation_ratio_critical           DOUBLE,
  critical_closed_no_escalation_rate  DOUBLE,
  closure_reason_entropy              DOUBLE,
  closure_reason_top_share            DOUBLE,
  fp_rate_critical                    DOUBLE,
  note_missing_rate                   DOUBLE,
  note_template_score                 DOUBLE,
  note_dup_cluster_share              DOUBLE,
  note_distinct_ratio                 DOUBLE,
  repeat_no_remediation_rate          DOUBLE,
  cross_period_repeat_rate            DOUBLE,
  coverage_gap_score                  DOUBLE,
  coverage_gap_score_tier1            DOUBLE,
  silent_asset_rate_tier1             DOUBLE,
  silent_asset_rate_tier1_hist        DOUBLE,
  criticality_volume_ratio            DOUBLE,
  volume_delta_pct                    DOUBLE,
  aact_inv_gap_30_wmean               DOUBLE,
  aact_inv_gap_30_max                 DOUBLE,
  aact_inv_rate_slope_30              DOUBLE,
  batch_close_score                   DOUBLE,
  val_err_rate                        DOUBLE,
  val_warn_rate                       DOUBLE,
  unknown_asset_alert_rate            DOUBLE,
  features_json      JSON,                     -- {feature: value} for every registered feature
  support_json       JSON,                     -- {feature: {n, flag: OK|LOW_N|DEGENERATE|MISSING}}
  peer_z_json        JSON,                     -- {feature: robust z}
  peer_pct_json      JSON,                     -- {feature: percentile 0..1}
  peer_group_id      VARCHAR,
  peer_level         INTEGER,
  peer_n             INTEGER,
  PRIMARY KEY (entity_id, submission_period, run_id)
);

CREATE TABLE IF NOT EXISTS peer_baselines (
  submission_period VARCHAR NOT NULL,
  peer_group_id     VARCHAR NOT NULL,
  peer_level        INTEGER,
  feature           VARCHAR NOT NULL,
  run_id            VARCHAR NOT NULL,
  n                 INTEGER,
  median            DOUBLE,
  mad               DOUBLE,
  mean              DOUBLE,
  std               DOUBLE,
  p10               DOUBLE,
  p25               DOUBLE,
  p75               DOUBLE,
  p90               DOUBLE,
  member_entity_ids VARCHAR[],
  PRIMARY KEY (submission_period, peer_group_id, feature, run_id)
);

CREATE TABLE IF NOT EXISTS findings (
  finding_id            VARCHAR PRIMARY KEY,
  run_id                VARCHAR NOT NULL,
  entity_id             VARCHAR NOT NULL,
  submission_period     VARCHAR NOT NULL,
  module                VARCHAR,               -- A | B
  finding_class         VARCHAR,               -- execution_gap | negative_space
  source                VARCHAR,               -- RULE | ML | COMBINED
  rule_id               VARCHAR,
  rule_version          VARCHAR,
  control_id            VARCHAR,
  capability            VARCHAR,
  scope                 VARCHAR,               -- entity | asset
  asset_id              VARCHAR,
  severity              VARCHAR,               -- LOW | MEDIUM | HIGH | CRITICAL
  p_rule                DOUBLE,
  p_ml                  DOUBLE,
  p_final               DOUBLE,
  calibrated            BOOLEAN,
  decision              VARCHAR,               -- AUTO_FLAG | MANUAL_REVIEW | AUTO_CLEAR
  t_star                DOUBLE,
  band_low              DOUBLE,
  band_high             DOUBLE,
  expected_cost         DOUBLE,
  priority_rank         INTEGER,
  title                 VARCHAR,
  rationale             VARCHAR,
  score_components_json JSON,
  shap_json             JSON,
  evidence_json         JSON,
  n_evidence_alerts     INTEGER,
  created_at            TIMESTAMP DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_findings_run ON findings (run_id, entity_id);

CREATE TABLE IF NOT EXISTS alert_sample_flags (
  flag_id           VARCHAR PRIMARY KEY,
  run_id            VARCHAR NOT NULL,
  entity_id         VARCHAR NOT NULL,
  submission_period VARCHAR NOT NULL,
  alert_id          VARCHAR NOT NULL,
  rule_ids          VARCHAR[],
  flag_source       VARCHAR,                   -- RULE | ML | BOTH
  p_alert           DOUBLE,
  decision          VARCHAR,
  queue_rank        INTEGER,
  queue_reason      VARCHAR,
  rationale         VARCHAR,
  shap_json         JSON,
  evidence_json     JSON,
  finding_id        VARCHAR,
  created_at        TIMESTAMP DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_asf_queue ON alert_sample_flags (run_id, entity_id, queue_rank);

CREATE TABLE IF NOT EXISTS sri_scores (
  entity_id                  VARCHAR NOT NULL,
  submission_period          VARCHAR NOT NULL,
  run_id                     VARCHAR NOT NULL,
  sri                        DOUBLE,
  band                       VARCHAR,
  confidence                 DOUBLE,
  dim_execution_gap          DOUBLE,
  dim_negative_space         DOUBLE,
  dim_escalation_discipline  DOUBLE,
  dim_investigation_quality  DOUBLE,
  dim_data_integrity         DOUBLE,
  dim_trend_penalty          DOUBLE,
  weights_hash               VARCHAR,
  components_json            JSON,             -- exact arithmetic per sub-indicator
  capability_json            JSON,             -- {capability: score} for the capability lens
  priority_score             DOUBLE,
  priority_rank              INTEGER,
  sri_delta_prev             DOUBLE,
  created_at                 TIMESTAMP DEFAULT current_timestamp,
  PRIMARY KEY (entity_id, submission_period, run_id)
);

CREATE TABLE IF NOT EXISTS trend_entity (
  entity_id               VARCHAR NOT NULL,
  submission_period       VARCHAR NOT NULL,
  run_id                  VARCHAR NOT NULL,
  sri                     DOUBLE,
  sri_delta               DOUBLE,
  sri_slope_3             DOUBLE,
  n_findings_a            INTEGER,
  n_findings_b            INTEGER,
  top_feature_deltas_json JSON,
  PRIMARY KEY (entity_id, submission_period, run_id)
);

-- ---------------------------------------------------------------------------
-- Governance: audit trail, supervisor feedback, model registry
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_runs (
  run_id               VARCHAR PRIMARY KEY,
  run_type             VARCHAR NOT NULL,       -- PIPELINE | INGEST | FEEDBACK | TRAIN | REPORT | RECALIBRATE | CONFIG
  submission_period    VARCHAR,
  triggered_by         VARCHAR,
  trigger_source       VARCHAR,                -- api | cli | test
  started_at           TIMESTAMP NOT NULL,
  finished_at          TIMESTAMP,
  status               VARCHAR,                -- RUNNING | SUCCESS | FAILED | SKIPPED_IDENTICAL
  app_version          VARCHAR,
  code_hash            VARCHAR,
  rules_version        VARCHAR,
  feature_version      VARCHAR,
  config_hash          VARCHAR,
  config_snapshot_json JSON,
  model_versions_json  JSON,
  input_manifest_json  JSON,
  input_hash           VARCHAR,
  output_manifest_json JSON,
  output_hash          VARCHAR,
  stage_log_json       JSON,                   -- [{stage, started, finished, rows, status, error}]
  error_text           VARCHAR,
  prev_run_hash        VARCHAR,
  run_hash             VARCHAR
);

CREATE TABLE IF NOT EXISTS feedback (
  feedback_id         VARCHAR PRIMARY KEY,
  run_id              VARCHAR,
  target_type         VARCHAR NOT NULL,        -- finding | alert_flag
  target_id           VARCHAR NOT NULL,
  entity_id           VARCHAR,
  submission_period   VARCHAR,
  rule_id             VARCHAR,
  decision            VARCHAR NOT NULL,        -- ACCEPT | REJECT | DEFER
  reviewer_id         VARCHAR,
  note                VARCHAR,
  p_at_decision       DOUBLE,
  model_versions_json JSON,
  created_at          TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS model_registry (
  model_name                VARCHAR NOT NULL,
  version                   VARCHAR NOT NULL,
  path                      VARCHAR,
  artifact_hash             VARCHAR,
  is_active                 BOOLEAN DEFAULT FALSE,
  trained_at                TIMESTAMP,
  trained_by_run_id         VARCHAR,
  training_periods          VARCHAR[],
  training_rows             INTEGER,
  training_data_hash        VARCHAR,
  feature_version           VARCHAR,
  feature_list_hash         VARCHAR,
  hyperparams_json          JSON,
  library_versions_json     JSON,
  metrics_json              JSON,
  parent_version            VARCHAR,
  superseded_by             VARCHAR,
  trained_on_feedback_count INTEGER,
  PRIMARY KEY (model_name, version)
);

CREATE TABLE IF NOT EXISTS config_history (
  config_hash   VARCHAR NOT NULL,
  saved_at      TIMESTAMP DEFAULT current_timestamp,
  saved_by      VARCHAR,
  snapshot_json JSON,
  note          VARCHAR
);
