"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  LayoutDashboard,
  Users,
  MapPin,
  Route,
  FileText,
  Shield,
  Settings,
  LogOut,
  TrendingUp,
  Satellite,
  Menu,
} from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/customers", label: "Customers", icon: Users },
  { href: "/routes", label: "Routes", icon: Route },
  { href: "/invoices", label: "Invoices", icon: FileText },
  { href: "/profitability", label: "Profitability", icon: TrendingUp },
  { href: "/satellite", label: "Satellite", icon: Satellite },
  { href: "/emd", label: "EMD Intel", icon: Shield },
  { href: "/settings", label: "Settings", icon: Settings },
];

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user, organizationName, logout } = useAuth();

  return (
    <>
      <div className="flex items-center gap-3 border-b px-4 py-4">
        <Image src="/logo.png" alt="QuantumPools" width={72} height={72} />
        <span className="text-lg font-semibold text-[#2989BE]">QuantumPools</span>
      </div>

      <nav className="flex-1 space-y-1 px-2 py-3">
        {navItems.map((item) => {
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
            </Link>
          );
        })}
      </nav>

      <div className="border-t p-4">
        <Link
          href="/settings"
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

  return (
    <>
      {/* Mobile hamburger — fixed top bar */}
      <div className="fixed top-0 left-0 right-0 z-40 flex h-14 items-center border-b bg-background px-4 sm:hidden">
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
        <span className="ml-2 text-sm font-semibold text-[#2989BE]">QuantumPools</span>
      </div>

      {/* Desktop sidebar */}
      <aside className="hidden sm:flex h-screen w-64 flex-col border-r bg-background">
        <SidebarContent />
      </aside>
    </>
  );
}
