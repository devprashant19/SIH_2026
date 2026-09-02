import { ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Figure } from "./primitives";
import { fmt2 } from "@/lib/format";
import type { Benchmark } from "@/api/types";

/** Strip plot of every peer's value with the selected entity marked. */
export function PeerDistributionChart({ data, entityId, height = 130, onSelect }: { data: Benchmark; entityId?: string; height?: number; onSelect?: (entityId: string) => void }) {
  const points = data.entities.filter((e) => e.value != null).map((e, i) => ({ ...e, y: (i % 3) - 1, isEntity: e.entity_id === entityId }));
  const peers = points.filter((p) => !p.isEntity);
  const mine = points.filter((p) => p.isEntity);
  const { median, p10, p90 } = data.stats;
  return (
    <Figure
      caption={`${data.label} across ${data.entities.length} peers. Median ${fmt2(median)}, p10–p90 ${fmt2(p10)}–${fmt2(p90)}. ${data.higher_is_worse ? "Higher is worse." : "Lower is worse."}`}
      table={{ headers: ["Entity", data.label], rows: data.entities.map((e) => [e.name, e.value == null ? null : fmt2(e.value)]) }}
    >
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <XAxis type="number" dataKey="value" name={data.label} tick={{ fontSize: 11 }} stroke="var(--color-text-muted)" />
          <YAxis type="number" dataKey="y" domain={[-2, 2]} hide />
          <ZAxis range={[60, 60]} />
          {p10 != null && p90 != null && <ReferenceArea x1={p10} x2={p90} fill="var(--color-risk-none-bg)" fillOpacity={0.9} />}
          {median != null && <ReferenceLine x={median} stroke="var(--color-text-muted)" strokeDasharray="3 3" label={{ value: "peer median", fontSize: 10, fill: "var(--color-text-muted)", position: "top" }} />}
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            contentStyle={{ fontSize: 12, background: "var(--color-bg)", border: "1px solid var(--color-border)" }}
            formatter={(v: number) => [fmt2(v), data.label]}
            labelFormatter={() => ""}
            content={({ payload }) => {
              const p = payload?.[0]?.payload;
              if (!p) return null;
              return (
                <div className="rounded-sm border border-border bg-bg p-2 text-xs">
                  <div className="font-medium">{p.name}</div>
                  <div className="tabular">{fmt2(p.value)}{p.percentile != null ? ` · ${Math.round(p.percentile * 100)}th percentile` : ""}</div>
                </div>
              );
            }}
          />
          <Scatter data={peers} fill="var(--color-text-muted)" onClick={(p: any) => onSelect?.(p.entity_id)} />
          <Scatter data={mine} fill="var(--color-accent)" shape="diamond" onClick={(p: any) => onSelect?.(p.entity_id)} />
        </ScatterChart>
      </ResponsiveContainer>
    </Figure>
  );
}
