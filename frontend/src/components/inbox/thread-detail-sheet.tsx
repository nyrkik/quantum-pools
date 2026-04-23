"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Loader2,
  Send,
  Pencil,
  AlertTriangle,
  User,
  ClipboardList,
  FileText,
  FolderOpen,
  X,
  Archive,
  ArchiveRestore,
  Trash2,
  CheckCheck,
} from "lucide-react";
import { useTeamMembersFull } from "@/hooks/use-team-members";
import { formatTime } from "@/lib/format";
import type { ThreadDetail } from "@/types/agent";
import { StatusBadge, UrgencyBadge, CategoryBadge } from "./inbox-badges";
import { CollapsibleBody } from "./collapsible-body";
import { ContactLearningPrompt, SENDER_TAG_STYLES } from "./contact-learning-modal";
import { RuleEditorDialog, type RuleDraft } from "./rule-editor-dialog";
import { LinkCasePicker } from "@/components/cases/link-case-picker";
import { AttachmentPicker, type UploadedAttachment } from "@/components/ui/attachment-picker";
import { AttachmentDisplay } from "@/components/ui/attachment-display";
import {
  ChevronDown,
  ChevronRight,
  ArrowDownLeft,
  ArrowUpRight,
  Eye,
  EyeOff,
  FolderInput,
  ShieldAlert,
  ShieldCheck,
  Tag,
  Bot,
  Check,
  Wand2,
  Clock,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { TimelineMessage } from "@/types/agent";

function stripHtmlToText(text: string): string {
  if (!text.includes("<") || !text.includes(">")) return text;
  // Only strip if it looks like actual HTML (has doctype, html tag, or multiple tags)
  if (!/<(!DOCTYPE|html|head|body|div|table|p\b)/i.test(text)) return text;
  // Normalize line endings first
  let clean = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  // Remove everything before <body> if present (kills <head>, <style>, doctype, etc.)
  const bodyStart = clean.search(/<body[^>]*>/i);
  if (bodyStart !== -1) {
    clean = clean.substring(clean.indexOf(">", bodyStart) + 1);
    clean = clean.replace(/<\/body>/i, "");
    clean = clean.replace(/<\/html>/i, "");
  } else {
    // No <body> tag — strip head/style/script manually
    clean = clean.replace(/<head[^>]*>[\s\S]*?<\/head>/gi, "");
  }
  // Remove any remaining style/script blocks
  clean = clean.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "");
  clean = clean.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "");
  clean = clean.replace(/<!--[\s\S]*?-->/g, "");
  // Block elements → newlines
  clean = clean.replace(/<br\s*\/?>/gi, "\n");
  clean = clean.replace(/<\/?(p|div|tr|li|h[1-6]|blockquote|td)[^>]*>/gi, "\n");
  // Strip remaining tags
  clean = clean.replace(/<[^>]+>/g, " ");
  // Decode common entities
  clean = clean.replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&#\d+;/g, "");
  // Collapse whitespace
  clean = clean.split("\n").map((l) => l.replace(/\s+/g, " ").trim()).join("\n");
  clean = clean.replace(/\n{3,}/g, "\n\n");
  return clean.trim();
}

function EmailMessage({
  msg,
  isInbound,
  isPending,
  timestamp,
  defaultExpanded,
}: {
  msg: TimelineMessage;
  isInbound: boolean;
  isPending: boolean;
  timestamp: string | null;
  defaultExpanded: boolean;
}) {
  const { organizationName } = useAuth();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isAutoSent = !isInbound && msg.status === "auto_sent";

  // Outbound sender name: user who sent it (approved_by) > org name > from_email
  const outboundName = msg.approved_by || organizationName || msg.from_email;

  // Preview: first line of body, truncated (strip HTML if present)
  const cleanBody = stripHtmlToText(msg.body || "");
  const preview = cleanBody.split("\n").find((l) => l.trim()) || "No content";

  if (!expanded) {
    // Collapsed: one-line clickable row
    return (
      <button
        onClick={() => setExpanded(true)}
        className="w-full flex items-center gap-2 mx-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors rounded text-sm group"
      >
        <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0 group-hover:text-foreground" />
        {isInbound ? (
          <ArrowDownLeft className="h-3 w-3 text-green-600 shrink-0" />
        ) : (
          <ArrowUpRight className="h-3 w-3 text-blue-500 shrink-0" />
        )}
        <span
          className="font-medium text-xs truncate w-32 shrink-0"
          title={isInbound ? msg.from_email : (msg.to_email || "")}
        >
          {isInbound ? (msg.from_name || msg.from_email.split("@")[0]) : isAutoSent ? "AI (auto)" : outboundName}
        </span>
        <span className="text-xs text-muted-foreground truncate flex-1">{preview.slice(0, 100)}</span>
        <span className="text-[10px] text-muted-foreground shrink-0 ml-2">
          {timestamp ? formatTime(timestamp) : ""}
        </span>
      </button>
    );
  }

  // Expanded: full email message as card
  const cardClasses = isPending
    ? "border-l-4 border-l-amber-400"
    : isAutoSent
    ? "border-l-4 border-l-sky-400 bg-sky-50/40 dark:bg-sky-950/10"
    : "";
  return (
    <div className={`mx-2 my-1.5 rounded-lg border shadow-sm ${isAutoSent ? "" : "bg-background"} ${cardClasses}`}>
      {/* Email header */}
      <button
        onClick={() => setExpanded(false)}
        className="w-full flex items-start gap-2 px-4 pt-3 pb-2 text-left hover:bg-muted/30 transition-colors rounded-t-lg"
      >
        <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0 mt-1" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {isInbound ? (
              <ArrowDownLeft className="h-3 w-3 text-green-600 shrink-0" />
            ) : (
              <ArrowUpRight className="h-3 w-3 text-blue-500 shrink-0" />
            )}
            <span className="text-sm font-medium">
              {isInbound
                ? (msg.from_name ? `${msg.from_name} <${msg.from_email}>` : msg.from_email)
                : isAutoSent ? "AI (auto-sent)" : outboundName}
            </span>
            {isAutoSent && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0 rounded text-[10px] font-medium bg-sky-100 dark:bg-sky-950/40 text-sky-700 dark:text-sky-400">
                <Bot className="h-2.5 w-2.5" />
                Auto
              </span>
            )}
            {!isInbound && !isAutoSent && msg.approved_by && organizationName && (
              <span className="text-[10px] text-muted-foreground">on behalf of {organizationName}</span>
            )}
            {!isInbound && (msg.delivery_status || msg.status === "failed" || msg.status === "queued") && (
              <DeliveryStatusChip
                status={msg.delivery_status || msg.status}
                error={msg.delivery_error}
                firstOpenedAt={msg.first_opened_at}
                openCount={msg.open_count}
              />
            )}
            <span className="text-xs text-muted-foreground ml-auto shrink-0">
              {timestamp ? formatTime(timestamp) : ""}
            </span>
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5 truncate">
            {isInbound ? (
              <>From: {msg.from_email} &middot; To: {msg.to_email}</>
            ) : (
              <>To: {msg.to_email}</>
            )}
          </div>
          {msg.subject && (
            <div className="text-xs text-muted-foreground mt-0.5">{msg.subject}</div>
          )}
        </div>
      </button>

      {/* Email body */}
      <div className="px-4 pb-4 pl-9 border-t border-dashed">
        {msg.body_html ? (
          <HtmlEmailBody html={msg.body_html} />
        ) : (
          <PlainTextBody text={stripHtmlToText(msg.body || "No content")} />
        )}
        {msg.attachments && msg.attachments.length > 0 && (
          <div className="mt-3">
            <AttachmentDisplay attachments={msg.attachments} />
          </div>
        )}
      </div>
    </div>
  );
}

function SenderTagChip({
  tag,
  senderEmail,
  threadId,
  onChanged,
  isClient,
}: {
  tag: string;
  senderEmail: string;
  threadId: string;
  onChanged: () => void;
  isClient?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [wholeDomain, setWholeDomain] = useState(false);
  const domain = senderEmail.includes("@") ? senderEmail.split("@")[1] : "";
  const hasTag = tag && tag.length > 0;
  const style = hasTag
    ? (SENDER_TAG_STYLES[tag] || SENDER_TAG_STYLES.other || { bg: "bg-gray-100", text: "text-gray-600" })
    : { bg: "bg-muted", text: "text-muted-foreground" };

  if (isClient) {
    return (
      <span
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text}`}
        title="Matched to a client"
      >
        <Tag className="h-2.5 w-2.5" />
        Client
      </span>
    );
  }

  const handleChangeTag = async (newTag: string) => {
    setSaving(true);
    try {
      await api.post("/v1/admin/agent-threads/dismiss-contact-prompt", {
        sender_email: wholeDomain && domain ? `*@${domain}` : senderEmail,
        reason: newTag,
      });
      toast.success(`Tag updated to "${newTag}"`);
      setOpen(false);
      onChanged();
    } catch {
      toast.error("Failed to update tag");
    } finally {
      setSaving(false);
    }
  };

  const TAGS = [
    { value: "billing", label: "Billing" },
    { value: "vendor", label: "Vendor" },
    { value: "business", label: "Business" },
    { value: "notification", label: "Notification" },
    { value: "personal", label: "Personal" },
    { value: "marketing", label: "Marketing" },
    { value: "other", label: "Other" },
    { value: "spam", label: "Spam" },
  ];

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text} hover:opacity-80 transition-opacity`}
          title={hasTag ? `Tagged: ${tag} — click to change` : "Tag this sender"}
        >
          <Tag className="h-2.5 w-2.5" />
          {hasTag ? tag.charAt(0).toUpperCase() + tag.slice(1) : "Tag"}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {domain && (
          <>
            <div className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
              <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
                <Checkbox checked={wholeDomain} onCheckedChange={(v) => setWholeDomain(!!v)} />
                All @{domain}
              </label>
            </div>
            <div className="h-px bg-border my-1" />
          </>
        )}
        {TAGS.map((t) => (
          <DropdownMenuItem
            key={t.value}
            onClick={() => handleChangeTag(t.value)}
            disabled={saving || t.value === tag}
            className={t.value === tag ? "font-medium" : ""}
          >
            {t.label}
            {t.value === tag && " (current)"}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function DeliveryStatusChip({
  status,
  error,
  firstOpenedAt,
  openCount,
}: {
  status: string;
  error?: string | null;
  firstOpenedAt?: string | null;
  openCount?: number;
}) {
  let bg = "bg-muted", text = "text-muted-foreground", label = status, icon = null;
  let title: string | undefined;
  if (status === "delivered") {
    bg = "bg-green-100 dark:bg-green-950/40";
    text = "text-green-700 dark:text-green-400";
    label = "Delivered";
  } else if (status === "opened") {
    bg = "bg-blue-100 dark:bg-blue-950/40";
    text = "text-blue-700 dark:text-blue-400";
    label = openCount && openCount > 1 ? `Opened (${openCount}x)` : "Opened";
    if (firstOpenedAt) title = `First opened ${new Date(firstOpenedAt).toLocaleString()}`;
  } else if (status === "bounced") {
    bg = "bg-red-100 dark:bg-red-950/40";
    text = "text-red-700 dark:text-red-400";
    label = "Bounced";
    title = error || undefined;
  } else if (status === "spam_complaint") {
    bg = "bg-red-100 dark:bg-red-950/40";
    text = "text-red-700 dark:text-red-400";
    label = "Spam complaint";
    title = error || undefined;
  } else if (status === "failed") {
    bg = "bg-red-100 dark:bg-red-950/40";
    text = "text-red-700 dark:text-red-400";
    label = "Send failed";
    title = error || "The email never reached the recipient. Re-send when the underlying issue is fixed.";
  } else if (status === "queued") {
    bg = "bg-amber-100 dark:bg-amber-950/40";
    text = "text-amber-700 dark:text-amber-400";
    label = "Sending…";
    title = "Send in progress. If this persists more than a couple minutes the janitor will flip it to failed.";
  }
  return (
    <span className={`inline-flex items-center px-1.5 py-0 rounded text-[10px] font-medium ${bg} ${text}`} title={title}>
      {icon}
      {label}
    </span>
  );
}

// Split plain text into (new content, quoted content)
function splitQuotedText(text: string): { newContent: string; quoted: string | null } {
  const patterns = [
    /\n?On [A-Za-z].{10,100}wrote:\s*\n/,
    /\n?-{3,}\s*(Forwarded|Original) Message[\s\S]*/,
    /\nFrom:\s*.+\nTo:\s*.+\n(?:Date|Sent):/,
    /\nSent from my (iPhone|iPad|Galaxy|device)/,
  ];
  for (const p of patterns) {
    const match = text.match(p);
    if (match && match.index !== undefined && match.index > 30) {
      return {
        newContent: text.substring(0, match.index).trim(),
        quoted: text.substring(match.index).trim(),
      };
    }
  }
  // Traditional > quoting
  const lines = text.split("\n");
  let quoteStart = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim().startsWith(">")) {
      quoteStart = i;
      break;
    }
  }
  if (quoteStart > 0) {
    return {
      newContent: lines.slice(0, quoteStart).join("\n").trim(),
      quoted: lines.slice(quoteStart).join("\n").trim(),
    };
  }
  return { newContent: text, quoted: null };
}

function PlainTextBody({ text }: { text: string }) {
  const [showQuoted, setShowQuoted] = useState(false);
  const { newContent, quoted } = splitQuotedText(text);

  return (
    <div className="pt-3 text-sm leading-relaxed break-words overflow-hidden">
      <div className="whitespace-pre-wrap">{newContent || "No content"}</div>
      {quoted && (
        <>
          <button
            onClick={() => setShowQuoted(!showQuoted)}
            className="mt-2 text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-muted/50 transition-colors"
          >
            <ChevronDown className={`h-3 w-3 transition-transform ${showQuoted ? "rotate-180" : ""}`} />
            {showQuoted ? "Hide quoted text" : "Show quoted text"}
          </button>
          {showQuoted && (
            <div className="mt-2 pl-3 border-l-2 border-muted whitespace-pre-wrap text-muted-foreground">
              {quoted}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Split HTML into (new content, quoted content) if a quote block is detected
function splitQuotedHtml(html: string): { newContent: string; quoted: string | null } {
  // Common Gmail/Outlook quote markers
  const markers = [
    /<div class="gmail_quote[\s\S]*$/i,                   // Gmail
    /<blockquote class="gmail_quote[\s\S]*$/i,            // Gmail
    /<div[^>]*id="appendonsend"[\s\S]*$/i,                // Outlook
    /<div[^>]*id="divRplyFwdMsg"[\s\S]*$/i,               // Outlook reply
    /<hr[^>]*id="stopSpelling"[\s\S]*$/i,                 // Outlook web
    /<div[^>]*style="[^"]*border[^"]*"[\s\S]*?From:[\s\S]*$/i, // Outlook "From:" block
    /<div[^>]*>-+\s*Original Message\s*-+[\s\S]*$/i,      // "Original Message"
    /<div[^>]*>-+\s*Forwarded message[\s\S]*$/i,          // Forwarded
    /(<p[^>]*>)?On [A-Za-z].{10,100}wrote:\s*<[\s\S]*$/i, // "On ... wrote:"
  ];
  for (const m of markers) {
    const match = html.match(m);
    if (match && match.index !== undefined && match.index > 100) {
      return {
        newContent: html.substring(0, match.index),
        quoted: html.substring(match.index),
      };
    }
  }
  return { newContent: html, quoted: null };
}

function HtmlEmailBody({ html }: { html: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(200);
  const [showQuoted, setShowQuoted] = useState(false);

  const { newContent, quoted } = splitQuotedHtml(html);
  const displayHtml = quoted && !showQuoted ? newContent : html;

  // Wrap the HTML in a minimal document with reset CSS to neutralize email client quirks
  const doc = `<!DOCTYPE html><html><head><meta charset="utf-8"><base target="_blank"><style>
    body { margin: 0; padding: 8px 0; font-family: system-ui, -apple-system, sans-serif; font-size: 14px; line-height: 1.5; color: #1f2937; word-wrap: break-word; }
    img { max-width: 100%; height: auto; }
    table { max-width: 100%; }
    a { color: #3b82f6; }
    * { max-width: 100% !important; }
    blockquote { margin: 0 0 0 1em; padding-left: 1em; border-left: 2px solid #e5e7eb; color: #6b7280; }
  </style></head><body>${displayHtml}</body></html>`;

  const resize = () => {
    if (!iframeRef.current) return;
    const d = iframeRef.current.contentDocument;
    if (!d) return;
    const newHeight = d.documentElement.scrollHeight;
    if (newHeight && newHeight !== height) setHeight(newHeight);
  };

  return (
    <div className="pt-3">
      <iframe
        ref={iframeRef}
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        srcDoc={doc}
        onLoad={resize}
        className="w-full border-0"
        style={{ height: `${height}px` }}
        title="Email body"
        key={showQuoted ? "full" : "new"}
      />
      {quoted && (
        <button
          onClick={() => { setShowQuoted(!showQuoted); setHeight(200); }}
          className="mt-1 text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-muted/50 transition-colors"
        >
          <ChevronDown className={`h-3 w-3 transition-transform ${showQuoted ? "rotate-180" : ""}`} />
          {showQuoted ? "Hide quoted text" : "Show quoted text"}
        </button>
      )}
    </div>
  );
}

function AutoHandledFeedbackBanner({
  threadId,
  senderEmail,
  category,
  senderTag,
  folderId,
  onFeedback,
}: {
  threadId: string;
  senderEmail: string | null;
  category: string | null;
  senderTag: string | null;
  folderId: string | null;
  onFeedback: (reloadThread: boolean) => void;
}) {
  const { role } = useAuth();
  const canReview = role === "owner" || role === "admin";
  const [reviewed, setReviewed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [folderName, setFolderName] = useState<string | null>(null);
  const [folders, setFolders] = useState<{ id: string; name: string }[]>([]);
  const [showRuleEditor, setShowRuleEditor] = useState(false);
  const [preview, setPreview] = useState<{
    state: "covered" | "promotable" | "unclear";
    rule_id?: string | null;
    rule_name?: string | null;
    append_value?: string | null;
  } | null>(null);
  const [appending, setAppending] = useState(false);

  useEffect(() => {
    api.get<{ folders: { id: string; name: string }[] }>("/v1/inbox-folders")
      .then((d) => {
        setFolders(d.folders || []);
        if (!folderId) {
          setFolderName("Inbox");
        } else {
          const f = d.folders.find((x) => x.id === folderId);
          setFolderName(f?.name || "Inbox");
        }
      })
      .catch(() => setFolderName(null));
  }, [folderId]);

  // Ask the backend whether an existing rule already covers this sender
  // or could cleanly accept it. Drives the three-state banner.
  useEffect(() => {
    if (!canReview) return;
    api.get<typeof preview>(
      `/v1/inbox-rules/match-preview?thread_id=${encodeURIComponent(threadId)}`,
    )
      .then((p) => setPreview(p))
      .catch(() => setPreview({ state: "unclear" }));
  }, [threadId, canReview]);

  const submit = async (correct: boolean) => {
    setSubmitting(true);
    try {
      await api.post("/v1/admin/agent-threads/auto-handled-feedback", {
        thread_id: threadId,
        was_correct: correct,
      });
      toast.success(correct ? "Got it — keep handling similar emails this way" : "Moved to Inbox — AI will learn");
      setReviewed(true);
      // Only reload the thread when we said "No" (thread was moved back to inbox + marked pending).
      // On "Yes" nothing in the thread changed — reloading would unmount the banner and reset reviewed state.
      onFeedback(!correct);
    } catch {
      toast.error("Failed to save feedback");
    } finally {
      setSubmitting(false);
    }
  };

  const initialRuleDraft = (): RuleDraft => {
    const sender = (senderEmail || "").toLowerCase();
    const actions: RuleDraft["actions"] = [];
    if (folderId) {
      actions.push({ type: "assign_folder", params: { folder_id: folderId } });
    }
    if (senderTag) {
      actions.push({ type: "assign_tag", params: { tag: senderTag } });
    }
    if (category && category !== "general") {
      actions.push({ type: "assign_category", params: { category } });
    }
    if (actions.length === 0) {
      actions.push({ type: "assign_folder", params: {} });
    }
    return {
      name: sender ? `Auto-handle ${sender}` : "New rule from inbox",
      priority: 100,
      conditions: sender
        ? [{ field: "sender_email", operator: "equals", value: sender }]
        : [],
      actions,
      is_active: true,
    };
  };

  const handleSaveRule = async (draft: RuleDraft) => {
    try {
      await api.post("/v1/inbox-rules", {
        name: draft.name || null,
        priority: draft.priority,
        conditions: draft.conditions,
        actions: draft.actions,
        is_active: draft.is_active,
      });
      // Record acceptance as well so the learning signal isn't lost.
      try {
        await api.post("/v1/admin/agent-threads/auto-handled-feedback", {
          thread_id: threadId,
          was_correct: true,
        });
      } catch {
        /* banner still proceeds to dismiss */
      }
      toast.success("Rule saved — AI will handle future matches automatically");
      setReviewed(true);
      onFeedback(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create rule");
      throw e;
    }
  };

  if (reviewed || !canReview) return null;

  // Describe what the AI actually did (shared across all three states).
  const actionSummary = (() => {
    const parts: string[] = [];
    if (folderName && folderName !== "Inbox") parts.push(`moved this to "${folderName}"`);
    else parts.push("auto-handled this");
    if (senderTag) parts.push(`tagged sender "${senderTag}"`);
    if (category && category !== "general") parts.push(`category "${category}"`);
    return parts.join(", ");
  })();

  // "Add sender to existing rule" — the State B happy-path click.
  const handleAppendToRule = async () => {
    if (!preview || preview.state !== "promotable" || !preview.rule_id || !preview.append_value) return;
    setAppending(true);
    try {
      await api.post(
        `/v1/inbox-rules/${preview.rule_id}/append-sender?thread_id=${encodeURIComponent(threadId)}`,
        { value: preview.append_value },
      );
      toast.success(
        preview.rule_name
          ? `Added to "${preview.rule_name}" rule`
          : "Added to existing rule",
      );
      setReviewed(true);
      onFeedback(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to add to rule");
    } finally {
      setAppending(false);
    }
  };

  // ------- STATE A: already covered by an existing rule -------
  if (preview?.state === "covered") {
    return (
      <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-purple-50 dark:bg-purple-950/30 border-b border-purple-200 dark:border-purple-800">
        <Check className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400 shrink-0" />
        <span className="text-xs text-purple-800 dark:text-purple-300 flex-1">
          Already covered by{" "}
          <span className="font-medium">
            {preview.rule_name || "an existing rule"}
          </span>
          . Future matches will keep auto-handling.
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 text-xs text-purple-700 hover:bg-purple-100 dark:hover:bg-purple-900/30"
          onClick={() => submit(true)}
          disabled={submitting}
        >
          Got it
        </Button>
      </div>
    );
  }

  // ------- STATE B: clean promotion to an existing rule -------
  if (preview?.state === "promotable") {
    return (
      <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-purple-50 dark:bg-purple-950/30 border-b border-purple-200 dark:border-purple-800">
        <Bot className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400 shrink-0" />
        <span className="text-xs text-purple-800 dark:text-purple-300 flex-1">
          AI {actionSummary}. Add{" "}
          <span className="font-mono text-[11px]">{preview.append_value}</span>{" "}
          to <span className="font-medium">{preview.rule_name || "the matching rule"}</span>?
        </span>
        <Button
          variant="default"
          size="sm"
          className="h-6 text-xs"
          onClick={handleAppendToRule}
          disabled={appending || submitting}
        >
          <Check className="h-3 w-3 mr-1" />
          {appending ? "Adding…" : "Add to rule"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 text-xs text-destructive hover:bg-destructive/10"
          onClick={() => submit(false)}
          disabled={submitting}
          title="Move to Inbox + AI learns"
        >
          <X className="h-3 w-3 mr-1" />
          Move to Inbox
        </Button>
      </div>
    );
  }

  // ------- STATE C: unclear — classic Yes / Create rule / No -------
  return (
    <>
      <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-purple-50 dark:bg-purple-950/30 border-b border-purple-200 dark:border-purple-800">
        <Bot className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400 shrink-0" />
        <span className="text-xs text-purple-800 dark:text-purple-300 flex-1">
          AI {actionSummary}. Was that right?
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 text-xs text-purple-700 hover:bg-purple-100 dark:hover:bg-purple-900/30"
          onClick={() => submit(true)}
          disabled={submitting}
        >
          <Check className="h-3 w-3 mr-1" />
          Yes
        </Button>
        {senderEmail && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs text-purple-700 hover:bg-purple-100 dark:hover:bg-purple-900/30"
            onClick={() => setShowRuleEditor(true)}
            disabled={submitting}
            title="Turn this into a permanent rule so future matches are auto-handled"
          >
            Create rule
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="h-6 text-xs text-destructive hover:bg-destructive/10"
          onClick={() => submit(false)}
          disabled={submitting}
          title="Move to Inbox + AI learns"
        >
          <X className="h-3 w-3 mr-1" />
          No, move to Inbox
        </Button>
      </div>
      {showRuleEditor && (
        <RuleEditorDialog
          open={showRuleEditor}
          onOpenChange={setShowRuleEditor}
          initialDraft={initialRuleDraft()}
          folders={folders}
          onSave={handleSaveRule}
        />
      )}
    </>
  );
}

interface InlineReplyProps {
  threadId: string;
  recipient: string;
  customerName: string | null;
  draftingFollowUp: boolean;
  onDraftFollowUp: () => void;
  followUp: { draft: string; to: string; subject: string } | null;
  followUpText: string;
  setFollowUpText: (v: string) => void;
  followUpRevise: string;
  setFollowUpRevise: (v: string) => void;
  followUpRevising: boolean;
  handleReviseFollowUp: () => void;
  followUpAttachments: UploadedAttachment[];
  setFollowUpAttachments: (a: UploadedAttachment[]) => void;
  sendingFollowUp: boolean;
  handleSendFollowUp: () => void;
  onCancel: () => void;
}

function InlineReplyComposer({
  threadId: _threadId,
  recipient,
  customerName,
  draftingFollowUp,
  onDraftFollowUp,
  followUp,
  followUpText,
  setFollowUpText,
  followUpRevise,
  setFollowUpRevise,
  followUpRevising,
  handleReviseFollowUp,
  followUpAttachments,
  setFollowUpAttachments,
  sendingFollowUp,
  handleSendFollowUp,
  onCancel,
}: InlineReplyProps) {
  const [expanded, setExpanded] = useState(false);
  const [manualText, setManualText] = useState("");

  // Expanded auto when an AI follow-up is drafted
  useEffect(() => {
    if (followUp) setExpanded(true);
  }, [followUp]);

  // Collapsed state: single-line click-to-expand bar
  if (!expanded && !followUp) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border bg-muted/30 hover:bg-muted/50 transition-colors text-left"
      >
        <Send className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="text-sm text-muted-foreground truncate">
          Reply to {customerName || recipient.split("@")[0]}…
        </span>
      </button>
    );
  }

  const handleSendManual = async () => {
    // Use the followUp send flow — need to populate followUpText first
    if (!followUp) {
      setFollowUpText(manualText);
      // Trigger send via the parent handler on next render
      setTimeout(() => handleSendFollowUp(), 0);
    } else {
      handleSendFollowUp();
    }
  };

  // Expanded state
  const displayText = followUp ? followUpText : manualText;
  const setDisplayText = followUp ? setFollowUpText : setManualText;

  return (
    <div className="rounded-lg border bg-background shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-muted/30">
        <Send className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="text-xs text-muted-foreground flex-1 truncate">
          To: <span className="text-foreground font-medium">{customerName || recipient}</span>
        </span>
        {!followUp && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[11px] gap-1"
            onClick={onDraftFollowUp}
            disabled={draftingFollowUp}
            title="AI drafts a proactive follow-up based on the conversation so far"
          >
            {draftingFollowUp ? <Loader2 className="h-3 w-3 animate-spin" /> : <Pencil className="h-3 w-3" />}
            Draft follow-up
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground"
          onClick={() => { setExpanded(false); setManualText(""); onCancel(); }}
          title="Close"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Body */}
      <div className="p-3 space-y-2">
        <Textarea
          value={displayText}
          onChange={(e) => setDisplayText(e.target.value)}
          placeholder="Write your reply..."
          className="text-sm min-h-[100px] border-0 shadow-none focus-visible:ring-0 p-0 resize-none"
          rows={4}
          autoFocus
        />

        {followUp && (
          <div className="flex gap-2 items-end pt-2 border-t">
            <Textarea
              value={followUpRevise}
              onChange={(e) => setFollowUpRevise(e.target.value)}
              placeholder="Tell AI how to change it..."
              className="text-sm min-h-[2rem] resize-none flex-1"
              rows={1}
              onInput={(e) => { const t = e.currentTarget; t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; }}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleReviseFollowUp(); } }}
            />
            <Button variant="outline" size="sm" className="h-8" onClick={handleReviseFollowUp} disabled={followUpRevising || !followUpRevise.trim()}>
              {followUpRevising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
            </Button>
          </div>
        )}

        <AttachmentPicker
          attachments={followUpAttachments}
          onAttachmentsChange={setFollowUpAttachments}
          sourceType="agent_message"
        />
      </div>

      {/* Send bar */}
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-t bg-muted/10">
        <span className="text-[10px] text-muted-foreground">
          {followUp ? "AI drafted — edit and send" : "Manual reply"}
        </span>
        <Button
          size="sm"
          onClick={handleSendManual}
          disabled={sendingFollowUp || !displayText.trim()}
          className="h-8"
        >
          {sendingFollowUp ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Send className="h-3.5 w-3.5 mr-1.5" />}
          Send
        </Button>
      </div>
    </div>
  );
}


function isStale(receivedAt: string | null) {
  if (!receivedAt) return false;
  return (Date.now() - new Date(receivedAt).getTime()) > 30 * 60 * 1000;
}

export function ThreadDetailSheet({
  threadId,
  onClose,
  onAction,
}: {
  threadId: string;
  onClose: () => void;
  onAction: () => void;
}) {
  const router = useRouter();
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  // Draft editing (for pending messages)
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [reviseInstruction, setReviseInstruction] = useState("");
  // AI draft panel collapses by default so the reading pane isn't dominated
  // by the draft editor. User clicks the "AI drafted a reply" bar to expand.
  const [draftExpanded, setDraftExpanded] = useState(false);
  const [revising, setRevising] = useState(false);
  // Linked-jobs panel + older-message accordion both collapse by default for
  // the same reason — keep the email body the dominant element of the panel.
  const [jobsExpanded, setJobsExpanded] = useState(false);
  const [olderMessagesExpanded, setOlderMessagesExpanded] = useState(false);

  // Follow-up (for handled threads)
  const [followUp, setFollowUp] = useState<{ draft: string; to: string; subject: string } | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [draftingFollowUp, setDraftingFollowUp] = useState(false);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);
  const [followUpRevise, setFollowUpRevise] = useState("");
  const [followUpRevising, setFollowUpRevising] = useState(false);
  const [approveAttachments, setApproveAttachments] = useState<UploadedAttachment[]>([]);
  const [followUpAttachments, setFollowUpAttachments] = useState<UploadedAttachment[]>([]);
  const [assigning, setAssigning] = useState(false);
  const [creatingJob, setCreatingJob] = useState(false);
  const [draftingEstimate, setDraftingEstimate] = useState(false);
  const [folders, setFolders] = useState<{ id: string; name: string; system_key: string | null }[]>([]);
  const teamMembers = useTeamMembersFull();

  const timelineEndRef = useRef<HTMLDivElement>(null);
  const newestMessageRef = useRef<HTMLDivElement>(null);

  // Load folders for move-to menu
  useEffect(() => {
    api.get<{ folders: { id: string; name: string; system_key: string | null }[] }>("/v1/inbox-folders")
      .then((d) => setFolders(d.folders))
      .catch(() => {});
  }, []);

  // On thread open (or when a new message lands), land at the TOP of the
  // newest message so the reader sees the start of what was last sent,
  // not the bottom of the thread. Email-client convention: you read a
  // message top-down; the thread pane should show the beginning of the
  // latest one, with older messages accessible by scrolling up.
  useEffect(() => {
    if (!thread?.timeline?.length) return;
    requestAnimationFrame(() => {
      newestMessageRef.current?.scrollIntoView({ block: "start" });
    });
  }, [thread?.id, thread?.timeline?.length]);

  const spamFolderId = folders.find((f) => f.system_key === "spam")?.id;
  const isInSpam = thread?.folder_id === spamFolderId;

  const handleMarkReadUnread = async () => {
    if (!thread) return;
    const action = thread.is_unread ? "mark-read" : "mark-unread";
    try {
      await api.post(`/v1/admin/agent-threads/bulk/${action}`, { thread_ids: [threadId] });
      loadThread();
      onAction();
    } catch { toast.error("Failed"); }
  };

  const handleSpamToggle = async () => {
    if (!thread) return;
    const action = isInSpam ? "not-spam" : "spam";
    try {
      await api.post(`/v1/admin/agent-threads/bulk/${action}`, { thread_ids: [threadId] });
      toast.success(isInSpam ? "Moved to Inbox" : "Marked as spam");
      onAction();
      onClose();
    } catch { toast.error("Failed"); }
  };

  const [moveAll, setMoveAll] = useState(true);

  const handleMoveToFolder = async (folderId: string | null) => {
    try {
      if (moveAll && thread) {
        await api.post("/v1/inbox-folders/move-sender", {
          sender_email: thread.contact_email,
          folder_id: folderId,
        });
        toast.success(`All from ${thread.contact_email.split("@")[0]} moved`);
      } else {
        await api.post("/v1/inbox-folders/move-thread", { thread_id: threadId, folder_id: folderId });
        toast.success("Moved");
      }
      loadThread();
      onAction();
    } catch { toast.error("Failed to move"); }
  };

  const loadThread = useCallback(() => {
    setLoading(true);
    api.get<ThreadDetail>(`/v1/admin/agent-threads/${threadId}`)
      .then((t) => {
        setThread(t);
        // Find latest pending message draft
        const pendingMsg = t.timeline.find((m) => m.status === "pending" && m.direction === "inbound" && m.draft_response);
        if (pendingMsg) {
          setEditText(pendingMsg.draft_response || "");
        }
      })
      .catch(() => toast.error("Failed to load thread"))
      .finally(() => setLoading(false));
  }, [threadId]);

  // When threadId changes (user clicked a different thread in the left
  // pane), clear local state so the detail pane shows a loading spinner
  // instead of the previously-rendered thread. Without this the old body,
  // draft, toolbar, etc. linger until the new fetch resolves.
  useEffect(() => {
    setThread(null);
    setEditText("");
    setReviseInstruction("");
    setDraftExpanded(false);
  }, [threadId]);

  useEffect(() => { loadThread(); }, [loadThread]);

  useEffect(() => {
    if (!loading && false) { // Disabled: email pane starts at top, not bottom
    }
  }, [loading, thread]);

  const pendingMessage = thread?.timeline.find((m) => m.status === "pending" && m.direction === "inbound");

  // Auto-generate a follow-up draft for handled customer threads so the
  // composer has a reply ready to review. Classifier deliberately skipped
  // drafting (category=no_response etc.), but Kim may still want to send
  // a warm acknowledgment with one click. Only fires when:
  //   - thread is matched to a customer (no point drafting for randoms)
  //   - status=handled (not already-pending — that flow has its own draft)
  //   - last message is inbound (AI just heard from the customer)
  //   - nothing has been auto-drafted already this mount
  const followUpAutoTriggeredRef = useRef<string | null>(null);
  useEffect(() => {
    if (!thread) return;
    if (followUpAutoTriggeredRef.current === thread.id) return;
    if (!thread.matched_customer_id) return;
    if (thread.status !== "handled") return;
    const lastMsg = thread.timeline[thread.timeline.length - 1];
    if (!lastMsg || lastMsg.direction !== "inbound") return;
    if (followUp || draftingFollowUp) return;
    followUpAutoTriggeredRef.current = thread.id;
    handleDraftFollowUp();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread?.id, thread?.matched_customer_id, thread?.status]);

  const handleApprove = async (responseText?: string) => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/approve`, {
        response_text: responseText || undefined,
        attachment_ids: approveAttachments.length ? approveAttachments.map((a) => a.id) : undefined,
      });
      toast.success("Reply sent");
      setApproveAttachments([]);
      onAction();
      onClose();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSending(false);
    }
  };

  const handleDismiss = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/dismiss`, {});
      toast.success("Thread dismissed");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to dismiss");
    } finally {
      setSending(false);
    }
  };

  const handleReviseDraft = async () => {
    if (!reviseInstruction.trim()) return;
    const currentDraft = editing ? editText : (pendingMessage?.draft_response || "");
    if (!currentDraft) return;
    setRevising(true);
    try {
      const result = await api.post<{ draft: string }>(`/v1/admin/agent-threads/${threadId}/revise-draft`, {
        draft: currentDraft,
        instruction: reviseInstruction,
      });
      if (editing) {
        // Update the textarea in-place
        setEditText(result.draft);
      } else {
        // Save revised draft directly and reload
        await api.post(`/v1/admin/agent-threads/${threadId}/save-draft`, { response_text: result.draft });
        loadThread();
      }
      setReviseInstruction("");
    } catch {
      toast.error("Failed to revise");
    } finally {
      setRevising(false);
    }
  };

  const handleDraftFollowUp = async () => {
    setDraftingFollowUp(true);
    try {
      const result = await api.post<{ draft: string; to: string; subject: string }>(`/v1/admin/agent-threads/${threadId}/draft-followup`, {});
      setFollowUp(result);
      setFollowUpText(result.draft);
    } catch {
      toast.error("Failed to draft follow-up");
    } finally {
      setDraftingFollowUp(false);
    }
  };

  const handleSendFollowUp = async () => {
    if (!followUpText.trim()) return;
    setSendingFollowUp(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/send-followup`, {
        response_text: followUpText,
        attachment_ids: followUpAttachments.length ? followUpAttachments.map((a) => a.id) : undefined,
      });
      toast.success("Follow-up sent");
      setFollowUp(null);
      setFollowUpText("");
      setFollowUpRevise("");
      setFollowUpAttachments([]);
      onAction();
      loadThread();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSendingFollowUp(false);
    }
  };

  const handleReviseFollowUp = async () => {
    if (!followUpRevise.trim() || !followUpText) return;
    setFollowUpRevising(true);
    try {
      const result = await api.post<{ draft: string }>(`/v1/admin/agent-threads/${threadId}/revise-draft`, {
        draft: followUpText,
        instruction: followUpRevise,
      });
      setFollowUpText(result.draft);
      setFollowUpRevise("");
    } catch {
      toast.error("Failed to revise");
    } finally {
      setFollowUpRevising(false);
    }
  };

  const handleMarkHandled = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/dismiss`, {});
      toast.success("Marked as handled");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to update");
    } finally {
      setSending(false);
    }
  };

  const handleArchive = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/archive`, {});
      toast.success("Thread archived");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to archive");
    } finally {
      setSending(false);
    }
  };

  const handleRestoreToInbox = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/restore-to-inbox`, {});
      toast.success("Moved to inbox");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to restore");
    } finally {
      setSending(false);
    }
  };

  const handleRetryOutbound = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/retry-outbound`, {});
      toast.success("Retry sent");
      await loadThread();
      onAction();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setSending(false);
    }
  };

  const handleDiscardOutbound = async () => {
    setSending(true);
    try {
      await api.post(`/v1/admin/agent-threads/${threadId}/discard-outbound`, {});
      toast.success("Discarded");
      await loadThread();
      onAction();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Discard failed");
    } finally {
      setSending(false);
    }
  };

  const handleDelete = async () => {
    setSending(true);
    try {
      await api.delete(`/v1/admin/agent-threads/${threadId}`);
      toast.success("Thread permanently deleted");
      onAction();
      onClose();
    } catch {
      toast.error("Failed to delete");
    } finally {
      setSending(false);
    }
  };

  const handleAssign = async (userId: string) => {
    setAssigning(true);
    try {
      const member = userId === "__unassign__" ? null : teamMembers.find((m) => m.user_id === userId);
      const result = await api.post<{ assigned_to_user_id: string | null; assigned_to_name: string | null; assigned_at: string | null }>(
        `/v1/admin/agent-threads/${threadId}/assign`,
        {
          user_id: member ? member.user_id : null,
          user_name: member ? `${member.first_name} ${member.last_name}` : null,
        },
      );
      if (thread) {
        setThread({
          ...thread,
          assigned_to_user_id: result.assigned_to_user_id,
          assigned_to_name: result.assigned_to_name,
          assigned_at: result.assigned_at,
        });
      }
      toast.success(member ? `Assigned to ${member.first_name}` : "Unassigned");
      onAction();
    } catch {
      toast.error("Failed to assign");
    } finally {
      setAssigning(false);
    }
  };

  const handleCreateCase = async () => {
    setCreatingJob(true);
    try {
      const result = await api.post<{ case_id: string; case_number?: string; already_exists?: boolean }>(`/v1/admin/agent-threads/${threadId}/create-case`, {});
      if (result.already_exists) {
        toast.info("Case already exists for this thread");
        router.push(`/cases/${result.case_id}`);
      } else {
        toast.success(`Case created: ${result.case_number}`);
        onAction();
        router.push(`/cases/${result.case_id}`);
      }
    } catch {
      toast.error("Failed to create case");
    } finally {
      setCreatingJob(false);
    }
  };

  const handleCreateJob = async () => {
    setCreatingJob(true);
    try {
      const result = await api.post<{ action_id: string; description: string; case_id?: string }>(`/v1/admin/agent-threads/${threadId}/create-job`, {});
      toast.success(`Job created: ${result.description}`);
      onAction();
      if (result.case_id) {
        router.push(`/cases/${result.case_id}`);
      } else {
        router.push(`/jobs?action=${result.action_id}`);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error && e.message ? e.message : "Failed to create job";
      toast.error(msg);
    } finally {
      setCreatingJob(false);
    }
  };

  const handleDraftEstimate = async () => {
    setDraftingEstimate(true);
    try {
      type DraftResult = {
        existing?: boolean;
        // New flow: proposal staged, awaits human accept.
        proposal_id?: string;
        status?: string;
        // Existing-invoice short-circuit: estimate already materialized.
        invoice_id?: string;
        invoice_number?: string;
        subject?: string;
        total?: number;
      };
      const result = await api.post<DraftResult>(
        `/v1/admin/agent-threads/${threadId}/draft-estimate`, {}
      );

      if (result.invoice_id) {
        // Pre-existing invoice already linked — toast + navigate (old behavior).
        toast.info(`Estimate ${result.invoice_number ?? ""} already exists`);
        onAction();
        onClose();
        router.push(`/invoices/${result.invoice_id}`);
        return;
      }

      // New flow: proposal staged. Send the user somewhere they can act
      // on it. Case detail is where the ProposalCard renders at the top
      // of the page, so the path is: draft → see draft → accept.
      if (result.existing) {
        toast.info("Estimate draft already pending — review and accept");
      } else {
        toast.success("Estimate drafted — review and accept to send to the customer");
      }
      onAction();
      if (thread?.case_id) {
        onClose();
        router.push(`/cases/${thread.case_id}`);
      }
      // If the thread has no case, keep the sheet open — the user can
      // navigate elsewhere or scroll to find the proposal in the summary.
      // (Future: render the ProposalCard inline in the sheet itself.)
    } catch {
      toast.error("Failed to draft estimate");
    } finally {
      setDraftingEstimate(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!thread) return null;

  // Identify the latest outbound message in the timeline. If it's in a stuck
  // state (queued/failed/bounced/delivery_error), show the Outbox banner with
  // Retry/Discard. Mirrors the server-side filter in list_threads and
  // InboxFolderService so the UI stays in sync with the folder count.
  const latestOutbound = [...thread.timeline]
    .reverse()
    .find((m) => m.direction === "outbound");
  const stuckOutbound =
    latestOutbound &&
    (
      latestOutbound.status === "failed" ||
      latestOutbound.status === "queued" ||
      latestOutbound.delivery_status === "bounced" ||
      latestOutbound.delivery_status === "spam_complaint" ||
      !!latestOutbound.delivery_error
    )
      ? latestOutbound
      : null;

  return (
    <div className="flex flex-col h-full overflow-x-hidden">
      {stuckOutbound && (
        <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800">
          <Clock className="h-4 w-4 text-amber-700 dark:text-amber-400 shrink-0" />
          <span className="flex-1 text-xs font-medium text-amber-900 dark:text-amber-200">
            Failed to send.
          </span>
          <Button
            variant="default"
            size="sm"
            className="h-7 text-xs shrink-0"
            onClick={handleRetryOutbound}
            disabled={sending}
          >
            {sending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
            Retry
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs shrink-0 text-destructive hover:bg-destructive/10"
            onClick={handleDiscardOutbound}
            disabled={sending}
          >
            Discard
          </Button>
        </div>
      )}
      {/* Compact toolbar — Status / Category / Stale badges intentionally
          moved to the left-pane thread table (scanning surface). Right pane
          keeps only the interactive controls: retag sender, add-as-contact
          prompt, and the icon actions on the right. */}
      <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 border-b bg-muted/30 flex-wrap">
        <SenderTagChip
          tag={thread.matched_customer_id ? "client" : (thread.sender_tag || "")}
          senderEmail={thread.contact_email}
          threadId={threadId}
          onChanged={() => { loadThread(); onAction(); }}
          isClient={!!thread.matched_customer_id}
        />
        {!thread.matched_customer_id && !thread.sender_tag && (
          <ContactLearningPrompt threadId={threadId} onContactSaved={() => { loadThread(); onAction(); }} />
        )}
        <div className="ml-auto flex items-center gap-0.5">
          {/* Group 1 — status: what state is this thread in */}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground"
            onClick={handleMarkReadUnread}
            title={thread.is_unread ? "Mark read" : "Mark unread"}
          >
            {thread.is_unread ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
          </Button>
          {(thread.has_pending || thread.status !== "handled") && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-green-600"
              onClick={handleMarkHandled}
              disabled={sending}
              title="Mark handled (no reply needed)"
            >
              <CheckCheck className="h-3.5 w-3.5" />
            </Button>
          )}

          <div className="h-4 w-px bg-border mx-1.5" aria-hidden />

          {/* Group 2 — place: where does this thread live */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground" title="Move to folder">
                <FolderInput className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <div className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
                  <Checkbox checked={moveAll} onCheckedChange={(v) => setMoveAll(!!v)} />
                  All from {thread.contact_email.split("@")[0]}
                </label>
              </div>
              <div className="h-px bg-border my-1" />
              <DropdownMenuItem onClick={() => handleMoveToFolder(null)}>Inbox</DropdownMenuItem>
              {folders.filter((f) => f.system_key !== "inbox").map((f) => (
                <DropdownMenuItem key={f.id} onClick={() => handleMoveToFolder(f.id)}>
                  {f.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground"
            onClick={handleSpamToggle}
            title={isInSpam ? "Not spam" : "Spam"}
          >
            {isInSpam ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground"
            onClick={() => router.push(`/inbox/rules?thread_id=${threadId}`)}
            title="Add to existing rule or create a new one"
          >
            <Wand2 className="h-3.5 w-3.5" />
          </Button>

          <div className="h-4 w-px bg-border mx-1.5" aria-hidden />

          {/* Group 3 — remove: destructive, placed last */}
          {thread.is_historical && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground"
              onClick={handleRestoreToInbox}
              title="Move to inbox"
            >
              <ArchiveRestore className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground"
            onClick={handleArchive}
            title="Archive"
          >
            <Archive className="h-3.5 w-3.5" />
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground hover:text-destructive"
                title="Delete"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Permanently delete this thread?</AlertDialogTitle>
                <AlertDialogDescription>This will remove the conversation and all messages. This cannot be undone.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <div className="w-px h-4 bg-border mx-0.5" />
          <Select
            value={thread.assigned_to_user_id || "__unassign__"}
            onValueChange={handleAssign}
            disabled={assigning}
          >
            <SelectTrigger className="h-6 text-[11px] w-36 border-dashed">
              <User className="h-3 w-3 mr-1 text-muted-foreground" />
              <SelectValue placeholder="Unassigned" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__unassign__">Unassigned</SelectItem>
              {teamMembers.map((m) => (
                <SelectItem key={m.user_id} value={m.user_id}>
                  {m.first_name} {m.last_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {assigning && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-destructive"
            onClick={onClose}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Auto-handled feedback banner (AI hid from inbox without sending a reply) */}
      {thread.is_auto_handled && (
        <AutoHandledFeedbackBanner
          threadId={threadId}
          senderEmail={thread.contact_email}
          category={thread.category}
          senderTag={thread.sender_tag}
          folderId={thread.folder_id}
          onFeedback={(reloadThread) => { if (reloadThread) loadThread(); onAction(); }}
        />
      )}

      {/* Email reading pane — when a thread has >3 messages, the older history is
          collapsed behind a single button so the latest message dominates. Pending
          inbound messages always render so they don't get hidden. */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden bg-muted/20 py-2">
        {(() => {
          const total = thread.timeline.length;
          const VISIBLE_RECENT = 2;
          const shouldCollapse = total > 3 && !olderMessagesExpanded;
          const visibleStartIdx = shouldCollapse ? total - VISIBLE_RECENT : 0;

          return (
            <>
              {total > 3 && (
                <button
                  type="button"
                  onClick={() => setOlderMessagesExpanded((x) => !x)}
                  className="mx-2 my-1.5 flex items-center gap-1.5 px-2 py-1.5 rounded hover:bg-muted/50 text-xs"
                >
                  {olderMessagesExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  <span className="font-medium text-muted-foreground">
                    Earlier messages ({total - VISIBLE_RECENT})
                  </span>
                </button>
              )}
              {thread.timeline.map((msg, idx) => {
                const isInbound = msg.direction === "inbound";
                const isPending = msg.status === "pending" && isInbound;
                if (shouldCollapse && idx < visibleStartIdx && !isPending) return null;
                const timestamp = isInbound ? msg.received_at : msg.sent_at;
                const isNewest = idx === total - 1;
                const content = (
                  <EmailMessage
                    key={msg.id}
                    msg={msg}
                    isInbound={isInbound}
                    isPending={isPending}
                    timestamp={timestamp}
                    defaultExpanded={isNewest || isPending}
                  />
                );
                return isNewest ? (
                  <div key={msg.id} ref={newestMessageRef}>{content}</div>
                ) : content;
              })}
            </>
          );
        })()}
        <div ref={timelineEndRef} />
      </div>

      {/* Bottom action area — capped so the reading pane keeps at least half the panel
          even when reply composer / linked jobs / actions are all expanded. */}
      <div className="flex-shrink-0 border-t pt-3 px-4 pb-3 space-y-2 overflow-x-hidden overflow-y-auto max-h-[50vh]">
        {/* AI draft — collapsed by default so the reading pane isn't dominated
            by the draft editor. Click the bar to review / edit / send. */}
        {pendingMessage && pendingMessage.draft_response && !draftExpanded && (
          <button
            onClick={() => setDraftExpanded(true)}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-950/50 transition-colors text-left"
          >
            <Pencil className="h-3.5 w-3.5 text-blue-700 dark:text-blue-400 shrink-0" />
            <span className="text-sm text-blue-700 dark:text-blue-400">Reply</span>
          </button>
        )}

        {pendingMessage && pendingMessage.draft_response && draftExpanded && (
          <div className="rounded-lg border bg-background shadow-sm">
            {/* Header — matches InlineReplyComposer */}
            <div className="flex items-center gap-2 px-3 py-2 border-b bg-blue-50 dark:bg-blue-950/30">
              <Pencil className="h-3.5 w-3.5 text-blue-700 dark:text-blue-400 shrink-0" />
              <span className="text-xs text-blue-700 dark:text-blue-400 flex-1 truncate">
                AI draft — review and send
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground"
                onClick={() => setDraftExpanded(false)}
                title="Collapse"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>

            {/* Body */}
            <div className="p-3 space-y-2">
              <Textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                className="text-sm min-h-[120px] border-0 shadow-none focus-visible:ring-0 p-0 resize-none"
                rows={6}
              />

              <div className="flex gap-2 items-end pt-2 border-t">
                <Textarea
                  value={reviseInstruction}
                  onChange={(e) => setReviseInstruction(e.target.value)}
                  placeholder="Tell AI how to change it..."
                  className="text-sm min-h-[2rem] resize-none flex-1"
                  rows={1}
                  onInput={(e) => { const t = e.currentTarget; t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; }}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleReviseDraft(); } }}
                />
                <Button variant="outline" size="sm" className="h-8" onClick={handleReviseDraft} disabled={revising || !reviseInstruction.trim()}>
                  {revising ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Revise
                </Button>
              </div>

              <AttachmentPicker
                attachments={approveAttachments}
                onAttachmentsChange={setApproveAttachments}
                sourceType="agent_message"
              />
            </div>

            {/* Send bar — matches InlineReplyComposer sizing/placement */}
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-t bg-muted/10">
              <span className="text-[10px] text-muted-foreground">AI drafted — edit and send</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8"
                  onClick={async () => {
                    try {
                      await api.post(`/v1/admin/agent-threads/${threadId}/save-draft`, { response_text: editText });
                      toast.success("Draft saved");
                      loadThread();
                    } catch { toast.error("Failed to save draft"); }
                  }}
                  disabled={sending}
                >
                  Save
                </Button>
                <Button size="sm" className="h-8" onClick={() => handleApprove(editText)} disabled={sending}>
                  {sending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Send className="h-3.5 w-3.5 mr-1.5" />}
                  Send
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Inline reply composer — visible whenever there isn't a draft
            to approve. Covers (a) no pending message at all (classic
            follow-up case) and (b) a pending inbound where draft generation
            failed or returned empty (don't leave the user with no reply UI). */}
        {(!pendingMessage || !pendingMessage.draft_response) && (
          <InlineReplyComposer
            threadId={threadId}
            recipient={thread.contact_email}
            customerName={thread.customer_name}
            draftingFollowUp={draftingFollowUp}
            onDraftFollowUp={handleDraftFollowUp}
            followUp={followUp}
            followUpText={followUpText}
            setFollowUpText={setFollowUpText}
            followUpRevise={followUpRevise}
            setFollowUpRevise={setFollowUpRevise}
            followUpRevising={followUpRevising}
            handleReviseFollowUp={handleReviseFollowUp}
            followUpAttachments={followUpAttachments}
            setFollowUpAttachments={setFollowUpAttachments}
            sendingFollowUp={sendingFollowUp}
            handleSendFollowUp={handleSendFollowUp}
            onCancel={() => { setFollowUp(null); setFollowUpText(""); setFollowUpRevise(""); }}
          />
        )}

        {/* Linked jobs — collapsed pill by default; expand inline on click. Keeps the
            email body dominant when a thread has many linked jobs. */}
        {Array.isArray(thread.actions) && thread.actions.length > 0 && (
          <div className="rounded border bg-muted/30 text-xs">
            <button
              type="button"
              onClick={() => setJobsExpanded((x) => !x)}
              className="w-full flex items-center gap-1.5 px-2 py-1.5 hover:bg-muted/50 rounded"
            >
              {jobsExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <span className="font-medium text-muted-foreground">Linked jobs ({thread.actions.length})</span>
            </button>
            {jobsExpanded && (
              <div className="px-2 pb-2 space-y-1">
                {thread.actions.map((raw) => {
                  const job = raw as { id: string; description: string | null; status: string };
                  return (
                    <div key={job.id} className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        className="text-left hover:underline truncate flex-1"
                        onClick={() => router.push(`/jobs?action=${job.id}`)}
                      >
                        {job.description || "(no description)"}
                      </button>
                      <Badge variant="outline" className="text-[10px] capitalize">{job.status}</Badge>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Quick actions: Link case, Add Job, Draft Estimate */}
        <div className="flex gap-2 flex-wrap items-center">
            <LinkCasePicker
              entityType="thread"
              entityId={thread.id}
              customerId={thread.matched_customer_id || undefined}
              currentCaseId={thread.case_id}
              currentCaseNumber={thread.case_number}
              currentCaseTitle={thread.case_title}
              onChange={() => { loadThread(); onAction(); }}
            />
            {thread.case_id && (
              <Button variant="outline" size="sm" onClick={handleCreateJob} disabled={creatingJob}>
                {creatingJob ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <ClipboardList className="h-3.5 w-3.5 mr-1.5" />}
                Add Job
              </Button>
            )}
            {thread.matched_customer_id && (
              thread.linked_estimate_invoice_id ? (
                // Estimate already accepted — navigate to the invoice.
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.push(`/invoices/${thread.linked_estimate_invoice_id}`)}
                >
                  <FileText className="h-3.5 w-3.5 mr-1.5" />
                  View Estimate →
                </Button>
              ) : thread.pending_estimate_proposal_id && thread.case_id ? (
                // Draft already staged — navigate to case where user accepts.
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { onClose(); router.push(`/cases/${thread.case_id}`); }}
                >
                  <FileText className="h-3.5 w-3.5 mr-1.5" />
                  View Draft →
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDraftEstimate}
                  disabled={draftingEstimate}
                >
                  {draftingEstimate ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <FileText className="h-3.5 w-3.5 mr-1.5" />}
                  Draft Estimate
                </Button>
              )
            )}
          </div>

      </div>
    </div>
  );
}
