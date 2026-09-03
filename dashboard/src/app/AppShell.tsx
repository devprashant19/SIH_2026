import { NavLink, Outlet, useSearchParams } from "react-router-dom";
import { useHealth, usePipelineStatus } from "@/api/hooks";
import { PeriodPicker } from "@/components/data/Pickers";
import { Toasts } from "@/components/ui/primitives";
import { HelpButton } from "@/guide/components/HelpDrawer";
import { TourController } from "@/guide/components/TourController";
import { cn } from "@/lib/cn";
import { fmtDateTime, shortHash } from "@/lib/format";
import { useUiStore } from "@/state/uiStore";
import { NAV_ITEMS } from "./router";

/** Global chrome: collapsible nav rail, period selector, and the provenance chip. */
export function AppShell() {
  const collapsed = useUiStore((s) => s.navCollapsed);
  const toggleNav = useUiStore((s) => s.toggleNav);
  const [params] = useSearchParams();
  const health = useHealth();
  const status = usePipelineStatus();
  const search = params.toString() ? `?${params.toString()}` : "";
  const lastRun = status.data?.last_run;

  return (
    <div className="flex h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-toast focus:bg-bg focus:p-2">
        Skip to content
      </a>
      <nav aria-label="Primary" className={cn("flex shrink-0 flex-col border-r border-border bg-surface transition-[width]", collapsed ? "w-[var(--nav-width-collapsed)]" : "w-[var(--nav-width)]")}>
        <div className="flex h-[var(--topbar-height)] items-center justify-between px-3">
          {!collapsed && (
            <span className="font-semibold tracking-tight" title="Supervisory Analytics Tool for SOC Assessment">
              SAT-SA
            </span>
          )}
          <button type="button" onClick={toggleNav} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} data-guide="global.nav-toggle" className="rounded-sm px-2 py-1 text-muted hover:bg-accent-bg hover:text-accent">
            {collapsed ? "»" : "«"}
          </button>
        </div>
        <ul className="flex flex-col gap-0.5 px-2" data-guide="global.nav">
          {NAV_ITEMS.map((item) => (
            <li key={item.key}>
              <NavLink
                to={{ pathname: item.to, search }}
                title={item.label}
                className={({ isActive }) => cn("block rounded-sm px-2 py-1.5 text-sm", isActive ? "bg-accent-bg font-medium text-accent" : "text-text hover:bg-accent-bg")}
              >
                {collapsed ? item.label.slice(0, 1) : item.label}
              </NavLink>
            </li>
          ))}
        </ul>
        {!collapsed && (
          <div className="mt-auto p-3 text-xs text-muted">
            <p>Supervisory analytics aid. Findings are indicators for examiner review, not conclusions.</p>
          </div>
        )}
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[var(--topbar-height)] shrink-0 items-center justify-between gap-3 border-b border-border px-4">
          <PeriodPicker />
          <span className="flex items-center gap-3">
            <HelpButton />
            <NavLink to={{ pathname: "/audit", search }} className="text-xs text-muted hover:text-accent" title="Provenance of the current results" data-guide="global.provenance">
            {health.data ? `v${health.data.app_version} · code ${shortHash(health.data.code_hash)} · config ${shortHash(health.data.config_hash)}` : "loading…"}
              {lastRun ? ` · last run ${fmtDateTime(lastRun.finished_at)}` : ""}
            </NavLink>
          </span>
        </header>
        <main id="main" className="min-w-0 flex-1 overflow-auto p-4">
          <Outlet />
        </main>
      </div>
      <Toasts />
      <TourController />
    </div>
  );
}
