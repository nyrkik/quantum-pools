"use client";

import { useState, useEffect, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ArrowLeft,
  FolderOpen,
  Mail,
  ClipboardList,
  FileText,
  MessageSquare,
  Loader2,
  Pencil,
  Check,
  CheckCircle2,
  X,
  Circle,
  Clock,
  Trash2,
  Plus,
} from "lucide-react";
import { toast } from "sonner";
import { ComposeMessage } from "@/components/messages/compose-message";
import { useCompose } from "@/components/email/compose-provider";
import { CaseDeepBlueCard } from "@/components/deepblue/case-deepblue-card";
import { useDeepBlueContext } from "@/components/deepblue/deepblue-provider";
import { useTeamMembers } from "@/hooks/use-team-members";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CaseStatusBadge,
  TimelineItem,
  JobCard,
  InvoiceCard,
  formatTime,
  JOB_TYPES,
} from "@/components/cases/case-components";
import type {
  CaseDetail,
  CaseJob,
  CaseThread,
  CaseInvoice,
  TimelineEntry,
} from "@/components/cases/case-components";

// --- Main Page ---

export default function CaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { openCompose } = useCompose();
  const teamMembers = useTeamMembers();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  useDeepBlueContext({ caseId: id, customerId: detail?.customer_id || undefined });
  const [loading, setLoading] = useState(true);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleInput, setTitleInput] = useState("");
  const [addingJob, setAddingJob] = useState(false);
  const [newJobDesc, setNewJobDesc] = useState("");
  const [newJobAssignee, setNewJobAssignee] = useState("");
  const [newJobDue, setNewJobDue] = useState("");
  const [newJobNotes, setNewJobNotes] = useState("");
  const [addingTask, setAddingTask] = useState(false);
  const [newTaskDesc, setNewTaskDesc] = useState("");
  const [newTaskAssignee, setNewTaskAssignee] = useState("");
  const [newTaskDue, setNewTaskDue] = useState("");
  const [composeOpen, setComposeOpen] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [editTaskDesc, setEditTaskDesc] = useState("");
  const [editTaskAssignee, setEditTaskAssignee] = useState("");
  const [editTaskDue, setEditTaskDue] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<CaseDetail>(`/v1/cases/${id}`);
      setDetail(data);
      setTitleInput(data.title);
    } catch {
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const handleAddJob = async () => {
    if (!newJobDesc.trim()) return;
    try {
      await api.post(`/v1/cases/${id}/jobs`, {
        description: newJobDesc.trim(),
        action_type: "repair",
        assigned_to: newJobAssignee || undefined,
        due_date: newJobDue || undefined,
      });
      setNewJobDesc("");
      setNewJobAssignee("");
      setNewJobDue("");
      setNewJobNotes("");
      setAddingJob(false);
      load();
    } catch { /* ignore */ }
  };

  const handleAddTask = async () => {
    if (!newTaskDesc.trim()) return;
    try {
      await api.post(`/v1/cases/${id}/jobs`, {
        description: newTaskDesc.trim(),
        action_type: "follow_up",
        assigned_to: newTaskAssignee || undefined,
        due_date: newTaskDue || undefined,
      });
      setNewTaskDesc("");
      setNewTaskAssignee("");
      setNewTaskDue("");
      setAddingTask(false);
      load();
    } catch { /* ignore */ }
  };

  const handleToggleTask = async (jobId: string, currentStatus: string) => {
    try {
      const newStatus = currentStatus === "done" ? "open" : "done";
      await api.put(`/v1/admin/agent-actions/${jobId}`, { status: newStatus });
      load();
    } catch { /* ignore */ }
  };

  const handleUpdateTask = async (jobId: string, updates: { description?: string; assigned_to?: string; due_date?: string }) => {
    try {
      await api.put(`/v1/admin/agent-actions/${jobId}`, updates);
      setEditingTaskId(null);
      load();
    } catch { /* ignore */ }
  };

  const handleDeleteTask = async (jobId: string) => {
    try {
      await api.put(`/v1/admin/agent-actions/${jobId}`, { status: "cancelled" });
      load();
    } catch { /* ignore */ }
  };

  const handleSaveTitle = async () => {
    if (!titleInput.trim() || !detail) return;
    try {
      await api.put(`/v1/cases/${id}`, { title: titleInput.trim() });
      setEditingTitle(false);
      load();
    } catch { /* ignore */ }
  };

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  if (!detail) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">Case not found</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => router.push("/cases")}>Back to Cases</Button>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="icon" className="h-8 w-8 mt-0.5 shrink-0" onClick={() => router.push("/cases")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
        </div>
        {detail.status !== "closed" ? (
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1.5 border-amber-300 text-amber-700 hover:bg-amber-50 hover:text-amber-800 shrink-0"
            onClick={async () => {
              try {
                await api.put(`/v1/cases/${id}`, { status: "closed" });
                toast.success("Case closed");
                load();
              } catch (_) { toast.error("Failed to close case"); }
            }}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Close Case
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1.5 shrink-0"
            onClick={async () => {
              try {
                await api.put(`/v1/cases/${id}`, { status: "open" });
                toast.success("Case reopened");
                load();
              } catch (_) { toast.error("Failed to reopen case"); }
            }}
          >
            <FolderOpen className="h-3.5 w-3.5" />
            Reopen
          </Button>
        )}
      </div>
      <div className="flex items-start gap-3">
        <div className="w-8 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-mono text-muted-foreground">{detail.case_number}</p>
          {editingTitle ? (
            <div className="flex items-center gap-1 mt-0.5">
              <Input
                value={titleInput}
                onChange={(e) => setTitleInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleSaveTitle(); if (e.key === "Escape") setEditingTitle(false); }}
                className="h-8 text-lg font-bold max-w-sm"
                autoFocus
              />
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleSaveTitle}>
                <Check className="h-3.5 w-3.5 text-muted-foreground hover:text-green-600" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setEditingTitle(false); setTitleInput(detail.title); }}>
                <X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold">{detail.title}</h1>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditingTitle(true)}>
                <Pencil className="h-3 w-3 text-muted-foreground" />
              </Button>
            </div>
          )}
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <CaseStatusBadge status={detail.status} />
            {detail.customer_name && (
              <Link href={`/customers/${detail.customer_id}`} className="text-sm text-muted-foreground hover:underline">
                {detail.customer_name}
              </Link>
            )}
            {detail.total_invoiced > 0 && (
              <span className="text-xs text-muted-foreground">
                ${detail.total_invoiced.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                {detail.total_paid > 0 && <span className="text-green-600 ml-1">(${detail.total_paid.toFixed(2)} paid)</span>}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Two-column layout: timeline left, panels right */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Timeline — left / full on mobile */}
        <div className="flex-1 min-w-0 order-2 lg:order-1">
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                Timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              {detail.timeline.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">No activity yet</p>
              ) : (
                <div className="divide-y">
                  {detail.timeline.map((entry) => (
                    <TimelineItem key={entry.id} entry={entry} jobs={detail.jobs} invoices={detail.invoices} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Side panels — right / top on mobile */}
        <div className="lg:w-80 xl:w-96 shrink-0 space-y-4 order-1 lg:order-2">
          {/* Tasks */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground" />
                  Tasks
                </CardTitle>
                <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => setAddingTask(!addingTask)}>
                  + Add
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-1">
              {addingTask && (
                <div className="space-y-1.5 p-2 border rounded-md bg-background">
                  <Input
                    value={newTaskDesc}
                    onChange={(e) => setNewTaskDesc(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && newTaskDesc.trim()) handleAddTask(); if (e.key === "Escape") setAddingTask(false); }}
                    placeholder="What needs to be done?"
                    className="h-7 text-xs"
                    autoFocus
                  />
                  <div className="flex gap-1.5">
                    <Select value={newTaskAssignee} onValueChange={setNewTaskAssignee}>
                      <SelectTrigger className="h-7 text-xs flex-1">
                        <SelectValue placeholder="Assign to..." />
                      </SelectTrigger>
                      <SelectContent>
                        {teamMembers.map((name) => (
                          <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      type="date"
                      value={newTaskDue}
                      onChange={(e) => setNewTaskDue(e.target.value)}
                      className="h-7 text-xs w-[130px]"
                    />
                  </div>
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={() => { setAddingTask(false); setNewTaskDesc(""); setNewTaskAssignee(""); setNewTaskDue(""); }}>
                      Cancel
                    </Button>
                    <Button size="sm" className="h-6 text-[10px]" onClick={handleAddTask} disabled={!newTaskDesc.trim()}>
                      Add Task
                    </Button>
                  </div>
                </div>
              )}
              {detail.jobs.filter(j => !JOB_TYPES.has(j.action_type) && j.status !== "cancelled").map((t) => {
                const isOverdue = t.due_date && new Date(t.due_date) < new Date() && t.status !== "done";
                const isEditing = editingTaskId === t.id;
                if (isEditing) {
                  return (
                    <div key={t.id} className="space-y-1.5 p-2 border rounded-md bg-background">
                      <Input value={editTaskDesc} onChange={(e) => setEditTaskDesc(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setEditingTaskId(null); }} className="h-7 text-xs" autoFocus />
                      <div className="flex gap-1.5">
                        <Select value={editTaskAssignee} onValueChange={setEditTaskAssignee}>
                          <SelectTrigger className="h-7 text-xs flex-1"><SelectValue placeholder="Assign to..." /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__" className="text-xs text-muted-foreground">Unassigned</SelectItem>
                            {teamMembers.map((name) => (<SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>))}
                          </SelectContent>
                        </Select>
                        <Input type="date" value={editTaskDue} onChange={(e) => setEditTaskDue(e.target.value)} className="h-7 text-xs w-[130px]" />
                      </div>
                      <div className="flex justify-between">
                        <Button variant="ghost" size="sm" className="h-6 text-[10px] text-destructive" onClick={() => { handleDeleteTask(t.id); setEditingTaskId(null); }}><Trash2 className="h-3 w-3 mr-1" /> Delete</Button>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={() => setEditingTaskId(null)}>Cancel</Button>
                          <Button size="sm" className="h-6 text-[10px]" onClick={() => handleUpdateTask(t.id, { description: editTaskDesc.trim() || undefined, assigned_to: editTaskAssignee === "__none__" ? "" : editTaskAssignee || undefined, due_date: editTaskDue || undefined })}>Save</Button>
                        </div>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={t.id} className="flex items-start gap-2 py-1.5 group">
                    <button onClick={() => handleToggleTask(t.id, t.status)} className="shrink-0 mt-0.5">
                      {t.status === "done" ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <Circle className="h-4 w-4 text-muted-foreground hover:text-green-500 transition-colors" />}
                    </button>
                    <div className="flex-1 min-w-0 cursor-pointer" onClick={() => { setEditingTaskId(t.id); setEditTaskDesc(t.description); setEditTaskAssignee(t.assigned_to || ""); setEditTaskDue(t.due_date ? t.due_date.split("T")[0] : ""); }}>
                      <span className={`text-xs ${t.status === "done" ? "line-through text-muted-foreground" : ""}`}>{t.description}</span>
                      <div className="flex items-center gap-2 mt-0.5">
                        {t.assigned_to && <span className="text-[10px] text-muted-foreground">{t.assigned_to}</span>}
                        {t.due_date && <span className={`text-[10px] ${isOverdue ? "text-red-500 font-medium" : "text-muted-foreground"}`}>{new Date(t.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>}
                      </div>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Jobs */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <ClipboardList className="h-3.5 w-3.5 text-muted-foreground" />
                  Jobs
                </CardTitle>
                <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => setAddingJob(!addingJob)}>
                  + Add
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {addingJob && (
                <div className="space-y-1.5 p-2 border rounded-md bg-background">
                  <Input
                    value={newJobDesc}
                    onChange={(e) => setNewJobDesc(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Escape") { setAddingJob(false); setNewJobDesc(""); } }}
                    placeholder="What needs to be done?"
                    className="h-7 text-xs"
                    autoFocus
                  />
                  <div className="flex gap-1.5">
                    <Select value={newJobAssignee} onValueChange={setNewJobAssignee}>
                      <SelectTrigger className="h-7 text-xs flex-1">
                        <SelectValue placeholder="Assign to..." />
                      </SelectTrigger>
                      <SelectContent>
                        {teamMembers.map((name) => (
                          <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      type="date"
                      value={newJobDue}
                      onChange={(e) => setNewJobDue(e.target.value)}
                      className="h-7 text-xs w-[130px]"
                    />
                  </div>
                  <Input
                    value={newJobNotes}
                    onChange={(e) => setNewJobNotes(e.target.value)}
                    placeholder="Description / notes (optional)"
                    className="h-7 text-xs"
                  />
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={() => { setAddingJob(false); setNewJobDesc(""); setNewJobAssignee(""); setNewJobDue(""); setNewJobNotes(""); }}>
                      Cancel
                    </Button>
                    <Button size="sm" className="h-6 text-[10px]" onClick={handleAddJob} disabled={!newJobDesc.trim()}>
                      Add Job
                    </Button>
                  </div>
                </div>
              )}
              {detail.jobs.filter(j => JOB_TYPES.has(j.action_type)).map((j) => (
                <JobCard key={j.id} job={j} />
              ))}
            </CardContent>
          </Card>

          {/* Messages */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
                  Messages
                </CardTitle>
                <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5" onClick={() => setComposeOpen(true)}>
                  + New
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {((detail as any).internal_threads || []).map((it: any) => (
                <div key={it.id} className="py-1 px-2 rounded-md bg-muted/30 text-xs">
                  <p className="font-medium truncate">{it.subject || "Team discussion"}</p>
                  <span className="text-muted-foreground">{it.message_count} message{it.message_count !== 1 ? "s" : ""}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Emails */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                  Emails
                </CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[10px] px-1.5"
                  onClick={() => openCompose({
                    customerId: detail.customer_id || undefined,
                    customerName: detail.customer_name || undefined,
                    subject: detail.title,
                    caseId: id,
                    onSent: load,
                  })}
                >
                  <Plus className="h-3 w-3 mr-0.5" /> Email
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {detail.threads.map((t) => (
                <div key={t.id} className="py-1 px-2 rounded-md bg-muted/30 text-xs">
                  <p className="font-medium truncate">{t.subject || "(no subject)"}</p>
                  <span className="text-muted-foreground">{t.contact_email} — {t.message_count} message{t.message_count !== 1 ? "s" : ""}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Documents */}
          <Card className="shadow-sm">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                  <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                  Documents
                </CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[10px] px-1.5"
                  onClick={() => router.push(`/invoices/new?type=estimate&customer=${detail.customer_id}&case=${id}`)}
                >
                  <Plus className="h-3 w-3 mr-0.5" /> Estimate
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {detail.invoices.map((inv) => (
                <InvoiceCard key={inv.id} invoice={inv} />
              ))}
            </CardContent>
          </Card>

          {/* DeepBlue */}
          <CaseDeepBlueCard
            caseId={id}
            customerId={detail.customer_id}
            conversations={detail.deepblue_conversations || []}
            onUpdate={load}
          />
        </div>
      </div>

      <ComposeMessage
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        onSent={() => { setComposeOpen(false); load(); }}
        defaultCaseId={id}
        defaultCustomerId={detail.customer_id || undefined}
      />
    </div>
  );
}
