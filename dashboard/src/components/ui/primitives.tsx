import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/state/uiStore";

export function Button({ variant = "default", className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "ghost" | "danger" }) {
  const styles = {
    default: "border border-border bg-bg hover:bg-surface",
    primary: "border border-accent bg-accent text-white hover:opacity-90",
    ghost: "border border-transparent hover:bg-surface",
    danger: "border border-risk-high text-risk-high hover:bg-risk-high-bg",
  }[variant];
  return <button type="button" className={cn("rounded-sm px-2.5 py-1 text-sm disabled:opacity-50 disabled:cursor-not-allowed", styles, className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn("rounded-sm border border-border bg-bg px-2 py-1 text-sm", className)} {...props}>
      {children}
    </select>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("card p-3", className)}>
      {(title || actions) && (
        <header className="mb-2 flex items-baseline justify-between gap-2">
          {typeof title === "string" ? <h2 className="text-sm font-semibold">{title}</h2> : title}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-2" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-4 rounded-sm bg-surface" />
      ))}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-border p-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="mt-1 text-sm text-muted">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="rounded-md border border-risk-high bg-risk-high-bg p-3 text-sm">
      <p className="font-medium text-risk-high">Could not load this view</p>
      <p className="mt-1 text-muted">{message}</p>
      {onRetry && (
        <Button className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

/** Wraps a query result: shows skeleton, error or the rendered children. */
export function QueryBoundary<T>({ query, children, rows = 4 }: { query: { data?: T; isLoading: boolean; error: unknown; refetch: () => void }; children: (data: T) => ReactNode; rows?: number }) {
  if (query.isLoading) return <Skeleton rows={rows} />;
  if (query.error) return <ErrorState error={query.error} onRetry={query.refetch} />;
  if (query.data === undefined) return <EmptyState title="No data" />;
  return <>{children(query.data)}</>;
}

export function Toasts() {
  const toasts = useUiStore((s) => s.toasts);
  const dismiss = useUiStore((s) => s.dismissToast);
  useEffect(() => {
    if (!toasts.length) return;
    const t = setTimeout(() => dismiss(toasts[0].id), 4000);
    return () => clearTimeout(t);
  }, [toasts, dismiss]);
  if (!toasts.length) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={cn("rounded-md border px-3 py-2 text-sm shadow-drawer", t.tone === "error" ? "border-risk-high bg-risk-high-bg text-risk-high" : "border-border bg-bg")}>
          {t.text}
        </div>
      ))}
    </div>
  );
}

export function Drawer({ open, onClose, title, children, width = "max-w-xl" }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        className={cn("h-full w-full overflow-auto border-l border-border bg-bg p-4 shadow-drawer", width)}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="mb-3 flex items-center justify-between gap-2">
          <div className="text-sm font-semibold">{title}</div>
          <Button variant="ghost" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: ReactNode }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-border">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          type="button"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={cn("-mb-px border-b-2 px-3 py-1.5 text-sm", active === t.key ? "border-accent font-medium text-accent" : "border-transparent text-muted hover:text-text")}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function HashChip({ hash, label }: { hash: string | null | undefined; label?: string }) {
  if (!hash) return <span className="text-muted">—</span>;
  return (
    <button
      type="button"
      title={`${label ? label + ": " : ""}${hash} (click to copy)`}
      onClick={() => navigator.clipboard?.writeText(hash)}
      className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-xs text-muted hover:text-accent"
    >
      {hash.slice(0, 8)}
    </button>
  );
}
