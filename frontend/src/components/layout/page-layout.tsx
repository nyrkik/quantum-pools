"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * PageLayout — standardized page structure for all dashboard pages.
 *
 * Usage:
 *   <PageLayout
 *     title="Invoices"
 *     subtitle="42 total"
 *     action={<Button><Plus /> Create</Button>}
 *     tabs={[
 *       { key: "invoices", label: "Invoices" },
 *       { key: "estimates", label: "Estimates" },
 *     ]}
 *     activeTab={tab}
 *     onTabChange={setTab}
 *   >
 *     {tab === "invoices" && <InvoicesContent />}
 *   </PageLayout>
 *
 * Change these components and ALL pages update. One place, one look.
 */

interface Tab {
  key: string;
  label: string;
  count?: number;
  badge?: ReactNode;
}

interface PageLayoutProps {
  title: string;
  subtitle?: string | ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  /** Secondary actions (right side, after primary action) */
  secondaryActions?: ReactNode;
  tabs?: Tab[];
  activeTab?: string;
  onTabChange?: (key: string) => void;
  /** Optional context section — stats, charts, filters between tabs and content */
  context?: ReactNode;
  children: ReactNode;
  className?: string;
  /**
   * When true, the layout becomes a flex column filling its parent: header
   * + tabs + context stay as fixed-height rows and the children region grows
   * to fill remaining space. Use for pages like the inbox where the content
   * area needs to own its own scroll (no outer page scroll that hides the
   * header's action buttons).
   */
  fullHeight?: boolean;
}

export function PageLayout({
  title,
  subtitle,
  icon,
  action,
  secondaryActions,
  tabs,
  activeTab,
  onTabChange,
  context,
  children,
  className,
  fullHeight,
}: PageLayoutProps) {
  return (
    <div
      className={cn(
        fullHeight ? "flex flex-col h-full min-h-0" : "space-y-6",
        className,
      )}
    >
      {/* Header — sticky at top of main's scroll container so action
          buttons (sync, settings, compose) stay reachable even if the
          content below overflows and the page scrolls. */}
      <div
        className={cn(
          "flex items-start justify-between gap-4 sticky top-0 z-20 bg-muted/40 py-2",
          fullHeight && "shrink-0 mb-2",
        )}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {icon}
            <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          </div>
          {subtitle && (
            <p className="text-sm text-muted-foreground mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
        {(action || secondaryActions) && (
          <div className="flex items-center gap-2 shrink-0">
            {secondaryActions}
            {action}
          </div>
        )}
      </div>

      {/* Tabs */}
      {tabs && tabs.length > 0 && (
        <div className={cn(fullHeight && "shrink-0")}>
          <PageTabs tabs={tabs} activeTab={activeTab} onTabChange={onTabChange} />
        </div>
      )}

      {/* Context section — stats, charts, filters */}
      {context && <div className={cn(fullHeight && "shrink-0")}>{context}</div>}

      {/* Content — grows to fill when fullHeight, else normal flow. */}
      {fullHeight ? (
        <div className="flex-1 min-h-0 flex flex-col">{children}</div>
      ) : (
        children
      )}
    </div>
  );
}

/**
 * PageTabs — the ONE tab component for the entire app.
 * Visually connected to content below. Clear active state.
 */
export function PageTabs({
  tabs,
  activeTab,
  onTabChange,
  className,
}: {
  tabs: Tab[];
  activeTab?: string;
  onTabChange?: (key: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("border-b", className)}>
      <nav className="flex gap-0 -mb-px" aria-label="Tabs">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => onTabChange?.(tab.key)}
              className={cn(
                "relative px-4 py-2.5 text-sm font-medium transition-colors whitespace-nowrap",
                "border-b-2 focus-visible:outline-none",
                isActive
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/30"
              )}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className={cn(
                  "ml-1.5 text-xs tabular-nums",
                  isActive ? "text-muted-foreground" : "text-muted-foreground/60"
                )}>
                  {tab.count}
                </span>
              )}
              {tab.badge}
            </button>
          );
        })}
      </nav>
    </div>
  );
}

/**
 * PageSection — optional wrapper for context/stats sections with consistent spacing.
 */
export function PageSection({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("", className)}>{children}</div>;
}
