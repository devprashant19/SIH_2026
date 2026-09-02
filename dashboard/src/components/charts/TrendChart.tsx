import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Figure } from "./primitives";
import { fmt1 } from "@/lib/format";

const SERIES_COLOURS = ["var(--color-cat-1)", "var(--color-cat-2)", "var(--color-cat-3)", "var(--color-cat-4)", "var(--color-cat-5)", "var(--color-cat-6)"];

export interface TrendSeriesSpec {
  key: string;
  label: string;
  values: (number | null)[];
  dashed?: boolean;
}

export function TrendChart({ periods, series, caption, height = 220, onPointClick, yLabel }: { periods: string[]; series: TrendSeriesSpec[]; caption: string; height?: number; onPointClick?: (period: string) => void; yLabel?: string }) {
  const data = periods.map((p, i) => {
    const row: Record<string, string | number | null> = { period: p };
    series.forEach((s) => (row[s.key] = s.values[i] ?? null));
    return row;
  });
  return (
    <Figure caption={caption} table={{ headers: ["Period", ...series.map((s) => s.label)], rows: periods.map((p, i) => [p, ...series.map((s) => (s.values[i] == null ? null : fmt1(s.values[i])))]) }}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }} onClick={(e: any) => e?.activeLabel && onPointClick?.(String(e.activeLabel))}>
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="period" tick={{ fontSize: 11 }} stroke="var(--color-text-muted)" />
          <YAxis tick={{ fontSize: 11 }} stroke="var(--color-text-muted)" width={40} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--color-text-muted)" } : undefined} />
          <Tooltip contentStyle={{ fontSize: 12, background: "var(--color-bg)", border: "1px solid var(--color-border)" }} formatter={(v: number, n: string) => [fmt1(v), n]} />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {series.map((s, i) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.dashed ? "var(--color-text-muted)" : SERIES_COLOURS[i % SERIES_COLOURS.length]}
              strokeDasharray={s.dashed ? "4 4" : undefined}
              strokeWidth={s.dashed ? 1.5 : 2}
              dot={{ r: 2.5 }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Figure>
  );
}
