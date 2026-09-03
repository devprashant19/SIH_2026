import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./AppShell";
import { PortfolioPage } from "@/features/portfolio/PortfolioPage";
import { EntityPage } from "@/features/entity/EntityPage";
import { FindingPage } from "@/features/finding/FindingPage";
import { FindingsListPage } from "@/features/finding/FindingsListPage";
import { QueuePage } from "@/features/queue/QueuePage";
import { PeerPage } from "@/features/peer/PeerPage";
import { CoveragePage } from "@/features/coverage/CoveragePage";
import { TrendsPage } from "@/features/trends/TrendsPage";
import { IngestionPage } from "@/features/ingestion/IngestionPage";
import { ConfigPage } from "@/features/config/ConfigPage";
import { AuditPage } from "@/features/audit/AuditPage";
import { ReportsPage } from "@/features/reports/ReportsPage";
import { PlaceholderPage } from "@/components/data/PlaceholderPage";
import { GuidePage } from "@/guide/GuidePage";

export const NAV_ITEMS = [
  { to: "/portfolio", label: "Portfolio", key: "portfolio" },
  { to: "/queue", label: "Review queue", key: "queue" },
  { to: "/findings", label: "Findings", key: "findings" },
  { to: "/peer", label: "Peer benchmarking", key: "peer" },
  { to: "/coverage", label: "Negative space", key: "coverage" },
  { to: "/trends", label: "Trends", key: "trends" },
  { to: "/ingestion", label: "Ingestion & data quality", key: "ingestion" },
  { to: "/config", label: "Configuration", key: "config" },
  { to: "/audit", label: "Audit log", key: "audit" },
  { to: "/reports", label: "Reports", key: "reports" },
  { to: "/guide", label: "How this works", key: "guide" },
] as const;

/** Every route pattern the app serves. The router and the guide's drift test both derive from
 *  this, so a route can only be added in one place. */
export const ROUTE_PATHS: readonly string[] = [
  "/portfolio",
  "/entities/:entityId",
  "/findings",
  "/findings/:findingId",
  "/queue",
  "/peer",
  "/coverage",
  "/trends",
  "/ingestion",
  "/config",
  "/audit",
  "/reports",
  "/guide",
];

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/portfolio" replace /> },
      { path: "portfolio", element: <PortfolioPage /> },
      { path: "entities/:entityId", element: <EntityPage /> },
      { path: "findings", element: <FindingsListPage /> },
      { path: "findings/:findingId", element: <FindingPage /> },
      { path: "queue", element: <QueuePage /> },
      { path: "peer", element: <PeerPage /> },
      { path: "coverage", element: <CoveragePage /> },
      { path: "trends", element: <TrendsPage /> },
      { path: "ingestion", element: <IngestionPage /> },
      { path: "config", element: <ConfigPage /> },
      { path: "audit", element: <AuditPage /> },
      { path: "reports", element: <ReportsPage /> },
      { path: "guide", element: <GuidePage /> },
      { path: "*", element: <PlaceholderPage title="Page not found" /> },
    ],
  },
]);
