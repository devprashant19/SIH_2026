import { useEffect, useMemo, useState } from "react";
import { useConfig, useConfigHistory, useSaveConfigMutation, useWhatIfMutation } from "@/api/hooks";
import { ThresholdLine } from "@/components/charts/primitives";
import { Button, Card, HashChip, QueryBoundary } from "@/components/ui/primitives";
import { guide } from "@/guide/model";
import { fmt1, fmt2, fmtDateTime } from "@/lib/format";
import { periodOrUndefined, usePeriodParam } from "@/state/useSearchParamState";
import { useUiStore } from "@/state/uiStore";

const CLASSES = ["execution_gap", "negative_space", "alert_sample"] as const;

export function ConfigPage() {
  const [period] = usePeriodParam();
  const config = useConfig();
  const history = useConfigHistory();
  const save = useSaveConfigMutation();
  const whatIf = useWhatIfMutation();
  const pushToast = useUiStore((s) => s.pushToast);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [costs, setCosts] = useState<Record<string, { C_FP: number; C_FN: number }>>({});
  const [rules, setRules] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const c = config.data;
    if (!c) return;
    setWeights(Object.fromEntries(Object.entries(c.sri_weights.dimensions).map(([k, v]) => [k, (v as any).weight])));
    setCosts(Object.fromEntries(CLASSES.map((cls) => [cls, { C_FP: c.costs.classes[cls]?.C_FP ?? 1, C_FN: c.costs.classes[cls]?.C_FN ?? 3 }])));
    setRules(Object.fromEntries(Object.entries(c.rules).map(([k, v]) => [k, (v as any).enabled])));
  }, [config.data]);

  const weightSum = useMemo(() => Object.values(weights).reduce((a, b) => a + b, 0), [weights]);
  const dirty = useMemo(() => {
    const c = config.data;
    if (!c) return false;
    const w = Object.entries(weights).some(([k, v]) => Math.abs(v - (c.sri_weights.dimensions[k as keyof typeof c.sri_weights.dimensions] as any).weight) > 1e-9);
    const co = CLASSES.some((cls) => costs[cls] && (costs[cls].C_FP !== (c.costs.classes[cls]?.C_FP ?? 1) || costs[cls].C_FN !== (c.costs.classes[cls]?.C_FN ?? 3)));
    const r = Object.entries(rules).some(([k, v]) => v !== (c.rules[k] as any).enabled);
    return w || co || r;
  }, [config.data, weights, costs, rules]);

  const applySave = () => {
    if (Math.abs(weightSum - 1) > 1e-6) {
      pushToast(`Dimension weights must sum to 1.00 (currently ${weightSum.toFixed(3)}).`, "error");
      return;
    }
    save.mutate(
      {
        sri_weights: { dimensions: Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, { weight: v }])) },
        costs: { classes: costs },
        rules: Object.fromEntries(Object.entries(rules).map(([k, v]) => [k, { enabled: v }])),
        note: "edited from the configuration screen",
        saved_by: "supervisor",
      },
      {
        onSuccess: (c) => pushToast(`Configuration saved (${c.config_hash.slice(0, 8)}). Re-run the analysis to apply it.`),
        onError: (e) => pushToast(e instanceof Error ? e.message : "Save failed", "error"),
      },
    );
  };

  const preview = () => whatIf.mutate({ period: periodOrUndefined(period), sri_weights: weights, costs });

  return (
    <QueryBoundary query={config} rows={10}>
      {(c) => (
        <div className="space-y-4">
          <header className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h1 className="text-xl font-semibold">Configuration</h1>
              <p className="text-sm text-muted">
                Everything the analytics depend on lives here and is hashed into every run. Current configuration <HashChip hash={c.config_hash} label="config" />
              </p>
            </div>
            <div className="flex items-center gap-2">
              {dirty && <span className="text-xs text-risk-elevated">unsaved changes</span>}
              <Button onClick={preview} disabled={whatIf.isPending} {...guide("config.preview")}>Preview impact</Button>
              <Button variant="primary" onClick={applySave} disabled={!dirty || save.isPending || Math.abs(weightSum - 1) > 1e-6} {...guide("config.save")}>
                Save
              </Button>
            </div>
          </header>

          <div className="grid gap-3 lg:grid-cols-2">
            <Card title="Supervisory Risk Indicator weights" actions={<span className={Math.abs(weightSum - 1) > 1e-6 ? "text-xs text-risk-high" : "text-xs text-muted"}>sum {weightSum.toFixed(2)}</span>}>
              <ul className="space-y-2" {...guide("config.weights")}>
                {Object.entries(c.sri_weights.dimensions).map(([key, dim]: [string, any]) => (
                  <li key={key} className="grid grid-cols-[minmax(140px,1fr)_70px_1fr] items-center gap-2 text-sm">
                    <label htmlFor={`w-${key}`}>{dim.label ?? key}</label>
                    <input
                      id={`w-${key}`}
                      type="number"
                      step="0.05"
                      min="0"
                      max="1"
                      className="w-full rounded-sm border border-border bg-bg px-2 py-1 tabular"
                      value={weights[key] ?? 0}
                      onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })}
                    />
                    <input type="range" min="0" max="1" step="0.05" value={weights[key] ?? 0} onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })} aria-label={`${dim.label ?? key} weight slider`} />
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">Sub-indicator weights are edited in config/sri_weights.yaml; the scorecard shows their effective weights after low-support redistribution.</p>
            </Card>

            <Card title="Cost of a wrong decision">
              <p className="text-sm text-muted">
                The decision threshold is derived, never guessed: <span className="font-mono">t* = C_FP / (C_FP + C_FN)</span>. Costing a missed weakness higher than an unnecessary review pushes the threshold down and favours recall.
              </p>
              <ul className="mt-2 space-y-3">
                {CLASSES.map((cls) => {
                  const cost = costs[cls] ?? { C_FP: 1, C_FN: 3 };
                  const t = cost.C_FP / (cost.C_FP + cost.C_FN);
                  const band = c.costs.classes[cls]?.band_halfwidth ?? c.costs.band_halfwidth;
                  return (
                    <li key={cls} className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="w-32 font-medium">{cls.replace(/_/g, " ")}</span>
                        <label className="inline-flex items-center gap-1">
                          <span className="text-muted">C_FP</span>
                          <input type="number" step="0.5" min="0.1" data-guide={cls === "execution_gap" ? "config.cost-cfp" : undefined} className="w-16 rounded-sm border border-border bg-bg px-1 py-0.5 tabular" value={cost.C_FP} onChange={(e) => setCosts({ ...costs, [cls]: { ...cost, C_FP: Number(e.target.value) } })} />
                        </label>
                        <label className="inline-flex items-center gap-1">
                          <span className="text-muted">C_FN</span>
                          <input type="number" step="0.5" min="0.1" data-guide={cls === "execution_gap" ? "config.cost-cfn" : undefined} className="w-16 rounded-sm border border-border bg-bg px-1 py-0.5 tabular" value={cost.C_FN} onChange={(e) => setCosts({ ...costs, [cls]: { ...cost, C_FN: Number(e.target.value) } })} />
                        </label>
                        <span className="tabular text-accent">t* = {t.toFixed(3)}</span>
                        <span className="text-xs text-muted">band ±{band}</span>
                      </div>
                      <span data-guide={cls === "execution_gap" ? "config.threshold-line" : undefined}>
                        <ThresholdLine tStar={t} band={band} />
                      </span>
                    </li>
                  );
                })}
              </ul>
            </Card>
          </div>

          {whatIf.data && (
            <Card title="Impact preview" actions={<span className="text-xs text-muted">Nothing is saved until you press Save</span>}>
              <p className="text-sm">
                Uncertain findings needing a human decision: <span className="tabular font-medium">{whatIf.data.n_uncertain_before}</span> now,{" "}
                <span className="tabular font-medium">{whatIf.data.n_uncertain_after}</span> with these settings.
              </p>
              <table className="mt-2 w-full text-sm">
                <caption className="sr-only">SRI under the proposed weights</caption>
                <thead>
                  <tr>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Entity</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">SRI now</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">SRI proposed</th>
                    <th scope="col" className="border-b border-border px-2 py-1 text-left">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {whatIf.data.rows.map((r) => {
                    const delta = (r.sri_what_if ?? 0) - (r.sri_current ?? 0);
                    return (
                      <tr key={r.entity_id} className="border-b border-border">
                        <td className="px-2 py-1.5">{r.entity_id} <span className="text-xs text-muted">{r.name}</span></td>
                        <td className="tabular px-2 py-1.5">{fmt1(r.sri_current)}</td>
                        <td className="tabular px-2 py-1.5">{fmt1(r.sri_what_if)}</td>
                        <td className={`tabular px-2 py-1.5 ${delta > 0.5 ? "text-risk-high" : delta < -0.5 ? "text-risk-low" : "text-muted"}`}>
                          {delta > 0 ? "+" : ""}{fmt1(delta)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          )}

          <Card title="Rules" actions={<span className="text-xs text-muted">{Object.values(rules).filter(Boolean).length} of {Object.keys(rules).length} enabled · thresholds live in config/rules.yaml</span>}>
            <table className="w-full text-sm" data-guide="config.rules">
              <caption className="sr-only">Rule catalogue</caption>
              <thead>
                <tr>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Enabled</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Rule</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Name</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Control</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Capability</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Weight</th>
                  <th scope="col" className="border-b border-border px-2 py-1 text-left">Parameters</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(c.rules).map(([id, r]: [string, any]) => (
                  <tr key={id} className="border-b border-border">
                    <td className="px-2 py-1.5">
                      <input type="checkbox" checked={rules[id] ?? true} onChange={(e) => setRules({ ...rules, [id]: e.target.checked })} aria-label={`Enable ${id}`} />
                    </td>
                    <td className="px-2 py-1.5 font-mono text-xs">{id}</td>
                    <td className="px-2 py-1.5">{r.name}</td>
                    <td className="px-2 py-1.5 text-xs text-muted">{c.controls?.[r.control_id] ?? r.control_id}</td>
                    <td className="px-2 py-1.5 text-xs text-muted">{r.capability}</td>
                    <td className="tabular px-2 py-1.5">{fmt2(r.prior_weight)}</td>
                    <td className="px-2 py-1.5 font-mono text-xs text-muted">{Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card title="Configuration history" data-guide="config.history">
            <QueryBoundary query={history} rows={3}>
              {(rows) =>
                rows.length ? (
                  <ul className="space-y-1 text-sm">
                    {rows.map((h) => (
                      <li key={`${h.config_hash}-${h.saved_at}`} className="flex flex-wrap items-center gap-2">
                        <HashChip hash={h.config_hash} label="config" />
                        <span className="text-muted">{fmtDateTime(h.saved_at)} · {h.saved_by}</span>
                        {h.note && <span>{h.note}</span>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted">No configuration changes recorded yet.</p>
                )
              }
            </QueryBoundary>
          </Card>
        </div>
      )}
    </QueryBoundary>
  );
}
