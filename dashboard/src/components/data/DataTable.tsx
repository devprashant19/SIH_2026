import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { EmptyState } from "@/components/ui/primitives";

interface Props<T> {
  data: T[];
  columns: ColumnDef<T, any>[];
  onRowClick?: (row: T) => void;
  rowKey?: (row: T) => string;
  emptyTitle?: string;
  emptyHint?: string;
  initialSort?: SortingState;
  dense?: boolean;
  isRowActive?: (row: T) => boolean;
  caption?: ReactNode;
}

export function DataTable<T>({ data, columns, onRowClick, rowKey, emptyTitle = "Nothing to show", emptyHint, initialSort = [], dense = true, isRowActive, caption }: Props<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSort);
  const table = useReactTable({ data, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  if (!data.length) return <EmptyState title={emptyTitle} hint={emptyHint} />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-full text-sm">
        {caption && <caption className="mb-2 text-left text-xs text-muted">{caption}</caption>}
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const sorted = h.column.getIsSorted();
                return (
                  <th
                    key={h.id}
                    scope="col"
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}
                    className="whitespace-nowrap border-b border-border px-2 py-1.5"
                  >
                    {h.isPlaceholder ? null : h.column.getCanSort() ? (
                      <button type="button" className="inline-flex items-center gap-1 hover:text-accent" onClick={h.column.getToggleSortingHandler()}>
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        <span aria-hidden className="text-[10px]">{sorted === "asc" ? "▲" : sorted === "desc" ? "▼" : "↕"}</span>
                      </button>
                    ) : (
                      flexRender(h.column.columnDef.header, h.getContext())
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={rowKey ? rowKey(row.original) : row.id}
              onClick={onRowClick ? () => onRowClick(row.original) : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row.original) : undefined}
              className={cn(
                "border-b border-border",
                dense ? "[&>td]:px-2 [&>td]:py-1.5" : "[&>td]:px-3 [&>td]:py-2",
                onRowClick && "cursor-pointer hover:bg-accent-bg",
                isRowActive?.(row.original) && "bg-accent-bg",
              )}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="align-top">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
