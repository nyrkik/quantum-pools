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
import type { Role } from "@/lib/permissions";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
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
  Wrench,
  LogOut,
  TrendingUp,
  Map,
  Menu,
  Code2,
  Bot,
  Mail,
  Bell,
  ClipboardList,
  Receipt,
  Package,
  MessageSquare,
} from "lucide-react";

const ALL_ROLES: Role[] = ["owner", "admin", "manager", "technician", "readonly"];

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, check: null },
  { href: "/customers", label: "Clients", icon: Users, check: null },
  { href: "/jobs", label: "Jobs", icon: ClipboardList, check: "canViewInbox" as keyof Permissions },
  { href: "/inbox", label: "Inbox", icon: Bot, check: "canViewInbox" as keyof Permissions, badge: "pending" as const },
  { href: "/messages", label: "Messages", icon: MessageSquare, check: null, badge: "messages" as const },
  { href: "/routes", label: "Routes", icon: Route, check: "canViewRoutes" as keyof Permissions },
  { href: "/invoices", label: "Invoices", icon: FileText, check: "canViewInvoices" as keyof Permissions },
  { href: "/parts", label: "Catalog", icon: Package, check: null },
  { href: "/map", label: "Map", icon: Map, check: "canViewSatellite" as keyof Permissions },
  { href: "/profitability", label: "Profitability", icon: TrendingUp, check: "canViewProfitability" as keyof Permissions },
  { href: "/inspections", label: "Inspections", icon: Shield, check: "canViewInspection" as keyof Permissions },
  { href: "/team", label: "Team", icon: UsersRound, check: "canViewTeam" as keyof Permissions },
  { href: "/settings", label: "Settings", icon: Settings, check: "canViewSettings" as keyof Permissions },
  { href: "/admin", label: "Admin", icon: Wrench, check: "canViewSettings" as keyof Permissions },
];

import { getBackendOrigin } from "@/lib/api";

function getBackendUrl(path: string) {
  if (typeof window === "undefined") return path;
  return `${getBackendOrigin()}${path}`;
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user, organizationName, branding, logout, refreshUser, roleVersion } = useAuth();
  const perms = usePermissions();
  const dev = useDevMode();
  const [pendingCount, setPendingCount] = useState(0);
  const [unreadMessages, setUnreadMessages] = useState(0);

  const fetchCounts = useCallback(() => {
    if (perms.canViewInbox) {
      api.get<{ pending: number }>("/v1/admin/agent-threads/stats")
        .then((s) => setPendingCount(s.pending ?? 0))
        .catch(() => {});
    }
    api.get<{ unread: number }>("/v1/messages/stats")
      .then((s) => setUnreadMessages(s.unread ?? 0))
      .catch(() => {});
  }, [perms.canViewInbox]);

  useEffect(() => {
    fetchCounts();
    const interval = setInterval(fetchCounts, 30000);
    return () => clearInterval(interval);
  }, [fetchCounts]);

  // Tab title with unread count
  useEffect(() => {
    const total = pendingCount + unreadMessages;
    document.title = total > 0 ? `(${total}) QuantumPools` : "QuantumPools";
  }, [pendingCount, unreadMessages]);

  const visibleNav = navItems.filter(
    (item) => item.check === null || perms[item.check] === true
  );

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
                <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[10px] font-semibold text-destructive-foreground">
                  {pendingCount}
                </span>
              )}
              {"badge" in item && item.badge === "messages" && unreadMessages > 0 && (
                <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-blue-500 px-1.5 text-[10px] font-semibold text-white">
                  {unreadMessages}
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
        <Link
          href="/profile"
          onClick={onNavigate}
          className="mb-3 flex items-center gap-3 rounded-md p-1 -mx-1 transition-colors hover:bg-accent/50"
        >
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
            {user?.first_name?.[0]}
            {user?.last_name?.[0]}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">
              {user?.first_name} {user?.last_name}
            </p>
            <p className="text-xs text-muted-foreground truncate">
              {organizationName}
            </p>
          </div>
        </Link>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-muted-foreground"
          onClick={() => logout()}
        >
          <LogOut className="mr-2 h-4 w-4" />
          Sign out
        </Button>
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
  const [unreadNotifs, setUnreadNotifs] = useState(0);
  const [lastRoleVersion, setLastRoleVersion] = useState(roleVersion);
  const [notifs, setNotifs] = useState<{ id: string; type: string; title: string; body: string | null; link: string | null; is_read: boolean; created_at: string }[]>([]);
  const [notifOpen, setNotifOpen] = useState(false);

  useEffect(() => {
    const poll = () => {
      if (perms.canViewInbox) {
        api.get<{ pending: number }>("/v1/admin/agent-threads/stats")
          .then((s) => setMobilePending(s.pending ?? 0))
          .catch(() => {});
      }
      api.get<{ unread: number; role_version?: number }>("/v1/notifications/count")
        .then((r) => {
          setUnreadNotifs(r.unread);
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

  const loadNotifs = async () => {
    try {
      const data = await api.get<{ id: string; type: string; title: string; body: string | null; link: string | null; is_read: boolean; created_at: string }[]>("/v1/notifications");
      setNotifs(data);
    } catch { /* ignore */ }
  };

  const handleBellClick = () => {
    if (!notifOpen) loadNotifs();
    setNotifOpen(!notifOpen);
  };

  const markAllRead = async () => {
    try {
      await api.post("/v1/notifications/read-all", {});
      setUnreadNotifs(0);
      setNotifs(prev => prev.map(n => ({ ...n, is_read: true })));
    } catch { /* ignore */ }
  };

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
          {unreadNotifs > 0 && (
            <button onClick={handleBellClick} className="relative">
              <Bell className="h-5 w-5 text-muted-foreground" />
              <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] font-bold text-white">
                {unreadNotifs}
              </span>
            </button>
          )}
          {mobilePending > 0 && (
            <Link href="/inbox" className="relative">
              <Mail className="h-5 w-5 text-muted-foreground" />
              <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[9px] font-bold text-destructive-foreground">
                {mobilePending}
              </span>
            </Link>
          )}
        </div>
      </div>

      {/* Notification dropdown (mobile + desktop) */}
      {notifOpen && (
        <div className="fixed top-14 right-4 z-50 w-80 max-h-96 overflow-y-auto rounded-lg border bg-background shadow-lg sm:top-4 sm:right-4">
          <div className="flex items-center justify-between px-3 py-2 border-b">
            <p className="text-sm font-medium">Notifications</p>
            {unreadNotifs > 0 && (
              <button onClick={markAllRead} className="text-xs text-primary hover:underline">Mark all read</button>
            )}
          </div>
          {notifs.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">No notifications</p>
          ) : (
            <div className="divide-y">
              {notifs.map((n) => (
                <div
                  key={n.id}
                  className={`px-3 py-2.5 text-sm cursor-pointer hover:bg-muted/50 ${!n.is_read ? "bg-blue-50/50 dark:bg-blue-950/20" : ""}`}
                  onClick={async () => {
                    if (!n.is_read) {
                      await api.post(`/v1/notifications/${n.id}/read`, {}).catch(() => {});
                      setUnreadNotifs(prev => Math.max(0, prev - 1));
                      setNotifs(prev => prev.map(x => x.id === n.id ? { ...x, is_read: true } : x));
                    }
                    if (n.link) { window.location.href = n.link; }
                    setNotifOpen(false);
                  }}
                >
                  <p className={`text-sm ${!n.is_read ? "font-medium" : ""}`}>{n.title}</p>
                  {n.body && <p className="text-xs text-muted-foreground mt-0.5">{n.body}</p>}
                  <p className="text-[10px] text-muted-foreground mt-1">
                    {new Date(n.created_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {notifOpen && <div className="fixed inset-0 z-40" onClick={() => setNotifOpen(false)} />}

      {/* Desktop sidebar */}
      <aside className="hidden sm:flex h-screen w-64 flex-col border-r bg-background relative">
        <SidebarContent />
        {unreadNotifs > 0 && (
          <button
            onClick={handleBellClick}
            className="absolute top-4 right-4 z-10 relative"
          >
            <Bell className="h-4 w-4 text-muted-foreground" />
            <span className="absolute -top-1.5 -right-1.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-amber-500 px-1 text-[8px] font-bold text-white">
              {unreadNotifs}
            </span>
          </button>
        )}
      </aside>
    </>
  );
}
