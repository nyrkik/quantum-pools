"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { X, FolderOpen } from "lucide-react";

const DISMISS_KEY = "cases-announcement-dismissed";

export function CasesAnnouncement() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(DISMISS_KEY)) {
      setVisible(true);
    }
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    setVisible(false);
  };

  return (
    <Card className="shadow-sm border-l-4 border-blue-500 mb-4">
      <CardContent className="py-4 pr-10 relative">
        <button onClick={dismiss} className="absolute top-3 right-3 text-muted-foreground hover:text-destructive">
          <X className="h-4 w-4" />
        </button>
        <div className="flex items-start gap-3">
          <div className="rounded-full bg-blue-100 dark:bg-blue-950 p-2 shrink-0 mt-0.5">
            <FolderOpen className="h-5 w-5 text-blue-600" />
          </div>
          <div className="space-y-2">
            <p className="text-sm font-semibold">Introducing Cases</p>
            <p className="text-xs text-muted-foreground">
              Everything related to a customer issue — emails, jobs, tasks, estimates, and team messages — is now grouped into a <strong>Case</strong>.
            </p>
            <div className="text-xs text-muted-foreground space-y-1">
              <p><strong>Cases</strong> is the new hub in the sidebar. Each case shows a timeline plus tiles for tasks, jobs, messages, emails, and documents.</p>
              <p><strong>Jobs</strong> are now created inside cases, not standalone. <strong>Tasks</strong> are lightweight action items with assignee and due date.</p>
              <p><strong>Inbox</strong> emails can be turned into a case with one click. <strong>Dashboard</strong> now shows your open cases.</p>
            </div>
            <p className="text-[11px] text-muted-foreground italic">All existing jobs and emails were automatically organized into cases.</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
