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
}: PageLayoutProps) {
  return (
    <div className={cn("space-y-6", className)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
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
        <PageTabs tabs={tabs} activeTab={activeTab} onTabChange={onTabChange} />
      )}

      {/* Context section — stats, charts, filters */}
      {context}

      {/* Content */}
      {children}
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
