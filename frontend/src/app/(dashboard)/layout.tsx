"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { WebSocketProvider } from "@/lib/ws";
import { DevModeProvider, useDevMode } from "@/lib/dev-mode";
import { ComposeProvider } from "@/components/email/compose-provider";
import { ComposeEmail } from "@/components/email/compose-email";
import { DeepBlueProvider } from "@/components/deepblue/deepblue-provider";
import { DeepBlueSheet } from "@/components/deepblue/deepblue-sheet";
import { DeepBlueTrigger } from "@/components/deepblue/deepblue-trigger";
import { Sidebar } from "@/components/layout/sidebar";
import { ActiveVisitBanner } from "@/components/layout/active-visit-banner";
import { FeedbackButton } from "@/components/feedback/feedback-button";
import { PageEmitter } from "@/components/events/page-emitter";
import { NavHistoryProvider } from "@/lib/nav-history";
import { Code2 } from "lucide-react";

function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!user) return null;

  const dev = useDevMode();

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {dev.isActive && (
          <div className="flex items-center justify-center gap-2 bg-amber-500 text-white text-xs font-medium py-1 px-4 shrink-0">
            <Code2 className="h-3 w-3" />
            <span>Dev Mode — Viewing as <span className="font-bold uppercase">{dev.effectiveRole}</span></span>
          </div>
        )}
        <ActiveVisitBanner />
        <main className="flex-1 overflow-y-auto overflow-x-hidden bg-muted/40 p-4 sm:p-6 pt-16 sm:pt-6">
          {children}
        </main>
        <FeedbackButton />
      </div>
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <WebSocketProvider>
        <DevModeProvider>
          <NavHistoryProvider>
            <ComposeProvider>
              <DeepBlueProvider>
                <AuthenticatedLayout>{children}</AuthenticatedLayout>
                <ComposeEmail />
                <DeepBlueTrigger />
                <DeepBlueSheet />
                <PageEmitter />
              </DeepBlueProvider>
            </ComposeProvider>
          </NavHistoryProvider>
        </DevModeProvider>
      </WebSocketProvider>
    </AuthProvider>
  );
}
