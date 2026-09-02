import { useNavigate } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/data/DataTable";
import { DecisionBadge, FeedbackBadge, RiskBadge, TypeBadge } from "@/components/domain/badges";
import { fmtProb } from "@/lib/format";
import type { FindingListItem } from "@/api/types";
import { DIMENSION_LABELS } from "@/components/charts/RiskHeatmap";

export function FindingsTable({ items, period, showEntity = false, emptyHint }: { items: FindingListItem[]; period: string; showEntity?: boolean; emptyHint?: string }) {
  const navigate = useNavigate();
  const columns: ColumnDef<FindingListItem, any>[] = [
    { accessorKey: "priority_rank", header: "#", cell: (c) => <span className="tabular text-muted">{c.getValue<number>()}</span>, size: 40 },
    { accessorKey: "severity", header: "Severity", cell: (c) => <RiskBadge band={c.getValue<any>()} compact /> },
    ...(showEntity ? [{ accessorKey: "entity_id", header: "Entity", cell: (c: any) => <span className="font-medium">{c.getValue()}</span> } as ColumnDef<FindingListItem, any>] : []),
    { accessorKey: "rule_id", header: "Rule", cell: (c) => <span className="font-mono text-xs">{c.getValue<string>() ?? "combined"}</span> },
    { accessorKey: "dimension", header: "Dimension", cell: (c) => <span className="text-muted">{DIMENSION_LABELS[c.getValue<keyof typeof DIMENSION_LABELS>()] ?? c.getValue<string>()}</span> },
    { accessorKey: "title", header: "Finding" },
    { accessorKey: "source", header: "Type", cell: (c) => <TypeBadge source={c.getValue<any>()} /> },
    { accessorKey: "p_final", header: "p", cell: (c) => <span className="tabular">{fmtProb(c.getValue<number>())}</span> },
    { accessorKey: "decision", header: "Decision", cell: (c) => <DecisionBadge decision={c.getValue<any>()} p={c.row.original.p_final} /> },
    { accessorKey: "feedback_status", header: "Review", cell: (c) => <FeedbackBadge status={c.getValue<string>()} /> },
  ];
  return (
    <DataTable
      data={items}
      columns={columns}
      rowKey={(r) => r.finding_id}
      onRowClick={(r) => navigate({ pathname: `/findings/${r.finding_id}`, search: `?period=${period}` })}
      emptyTitle="No findings for these filters"
      emptyHint={emptyHint}
      initialSort={[{ id: "priority_rank", desc: false }]}
    />
  );
}
