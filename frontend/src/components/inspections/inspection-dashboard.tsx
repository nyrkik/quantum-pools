"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ClipboardCheck,
  Loader2,
  X,
  Target,
  TrendingUp,
  Bell,
  ArrowUpRight,
} from "lucide-react";
import type { DashboardData, DashboardTile, ScraperHealth } from "./inspection-types";
import { formatDate } from "./inspection-constants";

interface InspectionDashboardProps {
  dashboard: DashboardData | null;
  expandedTile: DashboardTile;
  scraperHealth: ScraperHealth | null;
  onTileClick: (tile: DashboardTile) => void;
  onItemClick: (facilityId: string) => void;
}

export function InspectionDashboard({
  dashboard,
  expandedTile,
  scraperHealth,
  onTileClick,
  onItemClick,
}: InspectionDashboardProps) {
  return (
    <div className="shrink-0 space-y-2">
      {/* Backfill status bar — only show active/error, hide idle */}
      {scraperHealth?.state === "scraping" && (
        <div className="flex items-center gap-2 px-3 py-1 bg-green-50 dark:bg-green-950/30 border border-green-200/50 dark:border-green-800/50 rounded-md text-xs">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          <span className="text-green-700 dark:text-green-400 font-medium">Scraping new inspections</span>
        </div>
      )}
      {scraperHealth?.state === "error" && (
        <div className="flex items-center gap-2 px-3 py-1 bg-red-50 dark:bg-red-950/30 border border-red-200/50 dark:border-red-800/50 rounded-md text-xs">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500" />
          <span className="text-red-700 dark:text-red-400 font-medium">Scraper error</span>
          <span className="text-muted-foreground">{scraperHealth.consecutive_failures} consecutive failures</span>
        </div>
      )}

      {/* 4 Dashboard Tiles — compact */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        {/* Tile 1: My Inspections */}
        <Card
          className={`shadow-sm cursor-pointer transition-colors ${expandedTile === "inspections" ? "ring-2 ring-primary" : "hover:bg-accent/50"}`}
          onClick={() => onTileClick("inspections")}
        >
          <CardContent className="p-2.5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">My Inspections</p>
                {dashboard ? (
                  dashboard.my_inspections_this_week.length > 0 ? (
                    <div className="flex items-center gap-2 mt-0.5">
                      <p className="text-xl font-bold leading-tight text-primary">{dashboard.my_inspections_this_week.length}</p>
                      {dashboard.my_inspections_this_week.some(i => i.closure_required) ? (
                        <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
                      ) : (
                        <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground mt-1">No inspections this week</p>
                  )
                ) : (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-1" />
                )}
              </div>
              <ClipboardCheck className="h-5 w-5 text-primary opacity-40" />
            </div>
          </CardContent>
        </Card>

        {/* Tile 2: Alerts */}
        <Card
          className={`shadow-sm cursor-pointer transition-colors ${expandedTile === "alerts" ? "ring-2 ring-primary" : "hover:bg-accent/50"}`}
          onClick={() => onTileClick("alerts")}
        >
          <CardContent className="p-2.5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Alerts</p>
                {dashboard ? (
                  dashboard.season_alerts.length > 0 ? (
                    <div>
                      <p className="text-xl font-bold leading-tight mt-0.5 text-amber-600">{dashboard.season_alerts.length}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {dashboard.season_alerts.filter(a => a.alert_type === "recent_closure").length > 0
                          ? `${dashboard.season_alerts.filter(a => a.alert_type === "recent_closure").length} closures`
                          : `${dashboard.season_alerts.filter(a => a.alert_type === "repeat_violation").length} repeat violations`}
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground mt-1">No active alerts</p>
                  )
                ) : (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-1" />
                )}
              </div>
              <Bell className="h-5 w-5 text-amber-600 opacity-40" />
            </div>
          </CardContent>
        </Card>

        {/* Tile 3: Fresh Leads */}
        <Card
          className={`shadow-sm cursor-pointer transition-colors ${expandedTile === "leads" ? "ring-2 ring-primary" : "hover:bg-accent/50"}`}
          onClick={() => onTileClick("leads")}
        >
          <CardContent className="p-2.5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Fresh Leads</p>
                {dashboard ? (
                  <div>
                    <p className="text-xl font-bold leading-tight mt-0.5 text-green-600">{dashboard.fresh_leads.length}</p>
                    <p className="text-[10px] text-muted-foreground">inspected this week</p>
                  </div>
                ) : (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-1" />
                )}
              </div>
              <Target className="h-5 w-5 text-green-600 opacity-40" />
            </div>
          </CardContent>
        </Card>

        {/* Tile 4: Trending Worse */}
        <Card
          className={`shadow-sm cursor-pointer transition-colors ${expandedTile === "trending" ? "ring-2 ring-primary" : "hover:bg-accent/50"}`}
          onClick={() => onTileClick("trending")}
        >
          <CardContent className="p-2.5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Trending Worse</p>
                {dashboard ? (
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <p className="text-xl font-bold leading-tight text-red-600">{dashboard.trending_worse.length}</p>
                    <ArrowUpRight className="h-4 w-4 text-red-500" />
                  </div>
                ) : (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground mt-1" />
                )}
              </div>
              <TrendingUp className="h-5 w-5 text-red-600 opacity-40" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Expanded Alert Panel */}
      {expandedTile && dashboard && (
        <Card className="shadow-sm border-l-4 border-primary">
          <CardContent className="p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                {expandedTile === "inspections" && "My Inspections This Week"}
                {expandedTile === "alerts" && "Season Alerts"}
                {expandedTile === "leads" && "Fresh Leads"}
                {expandedTile === "trending" && "Trending Worse"}
              </span>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onTileClick(null)}>
                <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
              </Button>
            </div>

            {/* Inspections panel */}
            {expandedTile === "inspections" && (
              dashboard.my_inspections_this_week.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">No inspections for matched facilities this week.</p>
              ) : (
                <div className="space-y-1">
                  {dashboard.my_inspections_this_week.map((item, idx) => (
                    <button
                      key={idx}
                      className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm transition-colors"
                      onClick={() => onItemClick(item.facility_id)}
                    >
                      <div className="min-w-0 flex items-center gap-2">
                        <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${item.closure_required ? "bg-red-500" : item.total_violations > 0 ? "bg-amber-500" : "bg-green-500"}`} />
                        <span className="font-medium truncate">{item.facility_name}</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs text-muted-foreground">{formatDate(item.inspection_date)}</span>
                        {item.total_violations > 0 && (
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{item.total_violations} viol</Badge>
                        )}
                        {item.closure_required && (
                          <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Closure</Badge>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )
            )}

            {/* Alerts panel */}
            {expandedTile === "alerts" && (
              dashboard.season_alerts.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">No active alerts.</p>
              ) : (
                <div className="space-y-1">
                  {dashboard.season_alerts.map((alert, idx) => (
                    <button
                      key={idx}
                      className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm transition-colors"
                      onClick={() => onItemClick(alert.facility_id)}
                    >
                      <div className="min-w-0 flex items-center gap-2">
                        <Badge
                          variant={alert.alert_type === "recent_closure" ? "destructive" : "outline"}
                          className={`text-[10px] px-1.5 py-0 shrink-0 ${alert.alert_type === "repeat_violation" ? "border-amber-400 text-amber-600" : ""}`}
                        >
                          {alert.alert_type === "recent_closure" ? "Closure" : alert.alert_type === "repeat_violation" ? "Repeat" : "Unresolved"}
                        </Badge>
                        <span className="font-medium truncate">{alert.facility_name}</span>
                      </div>
                      <span className="text-xs text-muted-foreground shrink-0 max-w-[40%] truncate">{alert.description}</span>
                    </button>
                  ))}
                </div>
              )
            )}

            {/* Leads panel */}
            {expandedTile === "leads" && (
              dashboard.fresh_leads.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">No new leads this week.</p>
              ) : (
                <div className="space-y-1">
                  {dashboard.fresh_leads.map((lead, idx) => (
                    <button
                      key={idx}
                      className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm transition-colors"
                      onClick={() => onItemClick(lead.facility_id)}
                    >
                      <div className="min-w-0">
                        <span className="font-medium truncate block">{lead.facility_name}</span>
                        <span className="text-xs text-muted-foreground truncate block">{lead.address}</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{lead.total_violations} viol</Badge>
                        {lead.closure_required && (
                          <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Closure</Badge>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )
            )}

            {/* Trending panel */}
            {expandedTile === "trending" && (
              dashboard.trending_worse.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">No facilities trending worse.</p>
              ) : (
                <div className="space-y-1">
                  {dashboard.trending_worse.map((item, idx) => (
                    <button
                      key={idx}
                      className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm transition-colors"
                      onClick={() => onItemClick(item.facility_id)}
                    >
                      <span className="font-medium truncate">{item.facility_name}</span>
                      <div className="flex items-center gap-1 shrink-0 text-xs">
                        <span className="text-muted-foreground">{item.previous_violations}</span>
                        <ArrowUpRight className="h-3 w-3 text-red-500" />
                        <span className="text-red-600 font-medium">{item.recent_violations}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
