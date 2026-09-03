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
  /** Guide anchor for the table as a whole. */
  tableGuide?: string;
  /** Guide anchor applied to the first rendered row only, so "click the top row" is anchorable. */
  firstRowGuide?: string;
}

export function DataTable<T>({ data, columns, onRowClick, rowKey, emptyTitle = "Nothing to show", emptyHint, initialSort = [], dense = true, isRowActive, caption, tableGuide, firstRowGuide }: Props<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSort);
  const table = useReactTable({ data, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  if (!data.length) return <EmptyState title={emptyTitle} hint={emptyHint} />;
  return (
    <div className="overflow-x-auto" data-guide={tableGuide}>
      <table className="w-full min-w-full text-sm">
        {caption && <caption className="mb-2 text-left text-xs text-muted">{caption}</caption>}
        <thead className="sticky top-0 z-10 bg-surface backdrop-blur-md shadow-sm">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const sorted = h.column.getIsSorted();
                return (
                  <th
                    key={h.id}
                    scope="col"
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}
                    className="whitespace-nowrap border-b border-border px-3 py-2.5 text-left font-medium text-muted transition-colors hover:text-text"
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
          {table.getRowModel().rows.map((row, i) => (
            <tr
              key={rowKey ? rowKey(row.original) : row.id}
              data-guide={i === 0 ? firstRowGuide : undefined}
              onClick={onRowClick ? () => onRowClick(row.original) : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row.original) : undefined}
              className={cn(
                "border-b border-border transition-colors duration-150 group",
                dense ? "[&>td]:px-3 [&>td]:py-2" : "[&>td]:px-4 [&>td]:py-3",
                onRowClick && "cursor-pointer hover:bg-accent-bg/50 hover:shadow-sm relative z-0",
                isRowActive?.(row.original) && "bg-accent-bg/40 font-medium",
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
