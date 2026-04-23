"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import { usePermissions, type Permissions } from "@/lib/permissions";
import { useDevMode } from "@/lib/dev-mode";
import { useWSRefetch, useWSStatus } from "@/lib/ws";
import type { Role } from "@/lib/permissions";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  LayoutDashboard,
  Users,
  UsersRound,
  Route,
  FileText,
  Shield,
  ShieldCheck,
  Settings,
  LogOut,
  TrendingUp,
  Map,
  Menu,
  Code2,
  Bot,
  Mail,
  ClipboardList,
  FolderOpen,
  Receipt,
  Package,
  MessageSquare,
  MessageCircleQuestion,
  Sparkles,
} from "lucide-react";

const ALL_ROLES: Role[] = ["owner", "admin", "manager", "technician", "readonly"];

const navItems = [
  // Daily operations
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, check: null },
  { href: "/inbox", label: "Inbox", icon: Mail, check: "canViewInbox" as keyof Permissions, badge: "pending" as const },
  { href: "/messages", label: "Messages", icon: MessageSquare, check: null, badge: "messages" as const },
  { href: "/cases", label: "Cases", icon: FolderOpen, check: "canViewInbox" as keyof Permissions },
  { href: "/jobs", label: "Jobs", icon: ClipboardList, check: "canViewInbox" as keyof Permissions },
  { href: "/customers", label: "Clients", icon: Users, check: null },
  { href: "/routes", label: "Routes", icon: Route, check: "canViewRoutes" as keyof Permissions },
  { href: "/invoices", label: "Invoices", icon: FileText, check: "canViewInvoices" as keyof Permissions },
  // Tools & analysis
  { href: "/deepblue", label: "DeepBlue", icon: Sparkles, check: null },
  { href: "/map", label: "Map", icon: Map, check: "canViewSatellite" as keyof Permissions },
  { href: "/profitability", label: "Profitability", icon: TrendingUp, check: "canViewProfitability" as keyof Permissions },
  { href: "/inspections", label: "Inspections", icon: Shield, check: "canViewInspection" as keyof Permissions },
  { href: "/parts", label: "Catalog", icon: Package, check: null },
  // Admin
  { href: "/team", label: "Team", icon: UsersRound, check: "canViewTeam" as keyof Permissions },
  { href: "/settings", label: "Settings", icon: Settings, check: "canViewSettings" as keyof Permissions },
  { href: "/feedback", label: "Feedback", icon: MessageCircleQuestion, check: "canViewSettings" as keyof Permissions, badge: "feedback" as const },
  { href: "/dev", label: "Dev", icon: Code2, check: "__dev__" as const },
];

import { getBackendOrigin } from "@/lib/api";

function getBackendUrl(path: string) {
  if (typeof window === "undefined") return path;
  return `${getBackendOrigin()}${path}`;
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user, organizationName, branding, logout, refreshUser, roleVersion, isDeveloper } = useAuth();
  const perms = usePermissions();
  const dev = useDevMode();
  const [pendingCount, setPendingCount] = useState(0);
  const [unreadMessages, setUnreadMessages] = useState(0);
  const [openFeedback, setOpenFeedback] = useState(0);

  const fetchCounts = useCallback(() => {
    if (perms.canViewInbox) {
      api.get<{ pending: number; unread: number }>("/v1/admin/agent-threads/stats")
        .then((s) => setPendingCount(s.unread ?? 0))
        .catch(() => {});
    }
    api.get<{ unread: number }>("/v1/messages/stats")
      .then((s) => setUnreadMessages(s.unread ?? 0))
      .catch(() => {});
    if (dev.isDeveloper) {
      api.get<{ open: number }>("/v1/feedback/stats")
        .then((s) => setOpenFeedback(s.open ?? 0))
        .catch(() => setOpenFeedback(0));
    } else {
      setOpenFeedback(0);
    }
  }, [perms.canViewInbox, dev.isDeveloper]);

  const { isConnected: wsConnected } = useWSStatus();

  useEffect(() => {
    fetchCounts();
    // When WebSocket is connected, poll less frequently (safety net)
    // When disconnected, poll more aggressively
    const interval = setInterval(fetchCounts, wsConnected ? 60000 : 15000);
    return () => clearInterval(interval);
  }, [fetchCounts, wsConnected]);

  // Instant refetch on real-time events
  useWSRefetch(
    ["thread.new", "thread.updated", "thread.message.new", "message.new", "message.read", "notification.new"],
    fetchCounts,
    300,
  );

  // Tab title with unread count
  useEffect(() => {
    const total = pendingCount + unreadMessages;
    document.title = total > 0 ? `(${total}) QuantumPools` : "QuantumPools";
  }, [pendingCount, unreadMessages]);

  const visibleNav = navItems.filter((item) => {
    if (item.check === null) return true;
    if (item.check === "__dev__") return isDeveloper;
    return perms[item.check as keyof Permissions] === true;
  });

  const logoSrc = branding.logoUrl ? getBackendUrl(branding.logoUrl) : "/logo.png";
  const displayName = organizationName || "QuantumPools";

  return (
    <>
      <div className="flex flex-col items-center gap-1 border-b px-4 py-4">
        <Image src={logoSrc} alt={displayName} width={160} height={60} className="object-contain max-h-14" unoptimized />
        {!branding.logoUrl && (
          <span className="text-lg font-semibold text-center leading-tight" style={branding.primaryColor ? { color: branding.primaryColor } : undefined}>
            {displayName}
          </span>
        )}
      </div>

      <nav className="flex-1 space-y-1 px-2 py-3">
        {visibleNav.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
              {"badge" in item && item.badge === "pending" && pendingCount > 0 && (
                <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
                  {pendingCount}
                </span>
              )}
              {"badge" in item && item.badge === "messages" && unreadMessages > 0 && (
                <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-blue-500 px-1.5 text-[10px] font-semibold text-white">
                  {unreadMessages}
                </span>
              )}
              {"badge" in item && item.badge === "feedback" && openFeedback > 0 && (
                <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1.5 text-[10px] font-semibold text-white">
                  {openFeedback}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Dev mode panel */}
      {dev.isDeveloper && (
        <div className="border-t border-dashed border-amber-500/50 bg-amber-50 dark:bg-amber-950/30 px-3 py-3 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
              <Code2 className="h-3.5 w-3.5" />
              Dev Mode
            </div>
            <Switch
              checked={dev.isActive}
              onCheckedChange={dev.toggle}
              className="scale-75"
            />
          </div>
          {dev.isActive && (
            <>
              <Select
                value={dev.viewAsRole ?? dev.realRole}
                onValueChange={(v) => dev.setViewAs(v === dev.realRole ? null : v as Role)}
              >
                <SelectTrigger className="h-7 text-xs bg-white dark:bg-background">
                  <SelectValue placeholder="View as..." />
                </SelectTrigger>
                <SelectContent>
                  {ALL_ROLES.map((r) => (
                    <SelectItem key={r} value={r} className="text-xs">
                      {r === dev.realRole ? `${r} (you)` : r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {dev.orgs.length > 1 && (
                <Select
                  value={dev.activeOrgId || dev.orgs[0]?.id || ""}
                  onValueChange={(v) => dev.switchOrg(v === dev.orgs[0]?.id ? null : v)}
                >
                  <SelectTrigger className="h-7 text-xs bg-white dark:bg-background">
                    <SelectValue placeholder="Org..." />
                  </SelectTrigger>
                  <SelectContent>
                    {dev.orgs.map((o) => (
                      <SelectItem key={o.id} value={o.id} className="text-xs">
                        {o.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </>
          )}
        </div>
      )}

      <div className="px-4 py-1.5">
        <p className="text-[10px] text-muted-foreground/50 text-center">Powered by QuantumPools</p>
      </div>

      <div className="border-t p-4">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex w-full items-center gap-3 rounded-md p-1 -mx-1 transition-colors hover:bg-accent/50">
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                {user?.first_name?.[0]}
                {user?.last_name?.[0]}
              </div>
              <div className="min-w-0 text-left">
                <p className="text-sm font-medium truncate">
                  {user?.first_name} {user?.last_name}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {organizationName}
                </p>
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-48">
            <DropdownMenuItem asChild>
              <Link href="/profile" onClick={onNavigate} className="flex items-center gap-2">
                <Settings className="h-4 w-4" />
                Settings
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => logout()} className="text-destructive focus:text-destructive">
              <LogOut className="h-4 w-4 mr-2" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);
  const { organizationName, branding, roleVersion, refreshUser } = useAuth();
  const perms = usePermissions();
  const mobileDisplayName = organizationName || "QuantumPools";
  const [mobilePending, setMobilePending] = useState(0);
  const [lastRoleVersion, setLastRoleVersion] = useState(roleVersion);

  useEffect(() => {
    // Poll the inbox stats for the mobile-header pending badge, and the
    // notifications endpoint for `role_version` (used to refresh permissions
    // when an admin changes them). The unread count from notifications is
    // not displayed — see FB-22: the menu badges already cover it.
    const poll = () => {
      if (perms.canViewInbox) {
        api.get<{ pending: number; unread: number }>("/v1/admin/agent-threads/stats")
          .then((s) => setMobilePending(s.unread ?? 0))
          .catch(() => {});
      }
      api.get<{ unread: number; role_version?: number }>("/v1/notifications/count")
        .then((r) => {
          if (r.role_version !== undefined) {
            setLastRoleVersion((prev) => {
              if (prev !== r.role_version!) {
                refreshUser();
              }
              return r.role_version!;
            });
          }
        })
        .catch(() => {});
    };
    poll();
    const interval = setInterval(poll, 30000);
    return () => clearInterval(interval);
  }, [perms.canViewInbox, refreshUser]);

  return (
    <>
      {/* Mobile hamburger — fixed top bar */}
      <div className="fixed top-0 left-0 right-0 z-40 flex h-14 items-center justify-between border-b bg-background px-4 sm:hidden">
        <div className="flex items-center">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon">
                <Menu className="h-5 w-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-0">
              <div className="flex h-full flex-col">
                <SidebarContent onNavigate={() => setOpen(false)} />
              </div>
            </SheetContent>
          </Sheet>
          <span className="ml-2 text-sm font-semibold" style={branding.primaryColor ? { color: branding.primaryColor } : undefined}>
            {mobileDisplayName}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {mobilePending > 0 && (
            <Link href="/inbox" className="relative">
              <Mail className="h-5 w-5 text-muted-foreground" />
              <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[9px] font-bold text-primary-foreground">
                {mobilePending}
              </span>
            </Link>
          )}
        </div>
      </div>

      {/* Desktop sidebar */}
      <aside className="hidden sm:flex h-screen w-64 flex-col border-r bg-background relative">
        <SidebarContent />
      </aside>
    </>
  );
}
