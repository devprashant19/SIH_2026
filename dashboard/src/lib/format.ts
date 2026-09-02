const nf0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export const fmtInt = (v: number | null | undefined) => (v == null ? "—" : nf0.format(v));
export const fmt1 = (v: number | null | undefined) => (v == null ? "—" : nf1.format(v));
export const fmt2 = (v: number | null | undefined) => (v == null ? "—" : nf2.format(v));
export const fmtPct = (v: number | null | undefined, digits = 0) =>
  v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
export const fmtProb = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));

export function fmtMinutes(min: number | null | undefined): string {
  if (min == null) return "—";
  if (min < 60) return `${nf0.format(min)} min`;
  if (min < 60 * 24) return `${nf1.format(min / 60)} h`;
  return `${nf1.format(min / 1440)} d`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-IN", { hour12: false });
}

export const shortHash = (h: string | null | undefined, n = 8) => (h ? h.slice(0, n) : "—");
