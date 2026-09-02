import type { RiskBand, Decision } from "@/api/types";

/** SRI bands from config/sri_weights.yaml. Kept in sync with the backend. */
export function sriBand(score: number): RiskBand {
  if (score >= 75) return "CRITICAL";
  if (score >= 50) return "HIGH";
  if (score >= 25) return "ELEVATED";
  return "LOW";
}

export const BAND_LABEL: Record<RiskBand, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  ELEVATED: "Elevated",
  LOW: "Low",
};

/** Non-colour glyphs so severity is never conveyed by colour alone. */
export const BAND_GLYPH: Record<RiskBand, string> = {
  CRITICAL: "▲▲",
  HIGH: "▲",
  ELEVATED: "●",
  LOW: "▼",
};

export const BAND_CLASS: Record<RiskBand, string> = {
  CRITICAL: "text-risk-critical bg-risk-critical-bg",
  HIGH: "text-risk-high bg-risk-high-bg",
  ELEVATED: "text-risk-elevated bg-risk-elevated-bg",
  LOW: "text-risk-low bg-risk-low-bg",
};

export const DECISION_LABEL: Record<Decision, string> = {
  AUTO_FLAG: "Flagged",
  MANUAL_REVIEW: "Uncertain — recommend review",
  AUTO_CLEAR: "Cleared",
};
