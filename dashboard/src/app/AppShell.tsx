import { useEffect } from "react";
import { NavLink, Outlet, useSearchParams } from "react-router-dom";
import { useHealth, usePipelineStatus } from "@/api/hooks";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
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
  const theme = useUiStore((s) => s.theme);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }
  }, [theme]);

  return (
    <div className="flex h-full bg-bg relative overflow-hidden text-text selection:bg-accent selection:text-white">
      {/* Ambient background glows */}
      <div className="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] bg-accent-bg rounded-full filter blur-[100px] opacity-60 animate-pulse-slow pointer-events-none z-0" />
      <div className="absolute top-[60%] -right-[10%] w-[60%] h-[60%] bg-uncertain-bg rounded-full filter blur-[120px] opacity-40 pointer-events-none z-0" />
      
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-toast focus:bg-surface focus:p-2">
        Skip to content
      </a>
      <nav aria-label="Primary" className={cn("relative z-nav flex shrink-0 flex-col border-r border-border bg-surface backdrop-blur-xl transition-[width]", collapsed ? "w-[var(--nav-width-collapsed)]" : "w-[var(--nav-width)]")}>
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

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <header className="flex h-[var(--topbar-height)] shrink-0 items-center justify-between gap-3 border-b border-border bg-surface backdrop-blur-xl px-4 z-sticky sticky top-0">
          <PeriodPicker />
          <span className="flex items-center gap-3">
            <ThemeToggle />
            <HelpButton />
            <NavLink to={{ pathname: "/audit", search }} className="text-xs text-muted hover:text-accent" title="Provenance of the current results" data-guide="global.provenance">
            {health.data ? `v${health.data.app_version} · code ${shortHash(health.data.code_hash)} · config ${shortHash(health.data.config_hash)}` : "loading…"}
              {lastRun ? ` · last run ${fmtDateTime(lastRun.finished_at)}` : ""}
            </NavLink>
          </span>
        </header>
        <main id="main" className="min-w-0 flex-1 overflow-auto p-6 z-10 animate-fade-in relative">
          <Outlet />
        </main>
      </div>
      <Toasts />
      <TourController />
    </div>
  );
}
