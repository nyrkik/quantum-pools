"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Inbox,
  Send,
  Bot,
  ShieldAlert,
  Plus,
  Folder,
  Loader2,
  Mailbox,
  PenSquare,
} from "lucide-react";
import { useCompose } from "@/components/email/compose-provider";

export interface InboxFolderItem {
  id: string;
  name: string;
  icon: string | null;
  color: string | null;
  sort_order: number;
  is_system: boolean;
  system_key: string | null;
  thread_count: number;
  unread_count: number;
}

interface Props {
  selectedFolderId: string | null; // null = inbox
  onSelectFolder: (folderId: string | null, systemKey: string | null) => void;
  className?: string;
  refreshKey?: number; // increment to trigger reload
  autoHandledToday?: number; // shown as chip on Inbox row when > 0 (admin only)
}

const ICON_MAP: Record<string, React.ReactNode> = {
  inbox: <Inbox className="h-4 w-4" />,
  send: <Send className="h-4 w-4" />,
  bot: <Bot className="h-4 w-4" />,
  "shield-alert": <ShieldAlert className="h-4 w-4" />,
  mailbox: <Mailbox className="h-4 w-4" />,
};

export function InboxFolderSidebar({ selectedFolderId, onSelectFolder, className, refreshKey, autoHandledToday }: Props) {
  const { openCompose } = useCompose();
  const perms = usePermissions();
  const canSeeAllMail = perms.can("inbox.see_all_mail");
  const [folders, setFolders] = useState<InboxFolderItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ folders: InboxFolderItem[] }>("/v1/inbox-folders");
      setFolders(data.folders);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.post("/v1/inbox-folders", { name: newName.trim() });
      setNewName("");
      setShowCreate(false);
      await load();
    } catch {
      toast.error("Failed to create folder");
    } finally {
      setCreating(false);
    }
  };

  const isSelected = (folder: InboxFolderItem) => {
    if (folder.system_key === "inbox" && selectedFolderId === null) return true;
    return folder.id === selectedFolderId;
  };

  if (loading) {
    return (
      <div className={cn("flex items-center justify-center py-6", className)}>
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const inboxFolder = folders.find((f) => f.system_key === "inbox");
  const systemFolders = folders.filter((f) => {
    if (!f.is_system || f.system_key === "inbox") return false;
    // All Mail is permission-gated
    if (f.system_key === "all" && !canSeeAllMail) return false;
    return true;
  });
  const customFolders = folders.filter((f) => !f.is_system);

  const renderFolder = (f: InboxFolderItem, indent = false) => (
    <button
      key={f.id}
      onClick={() => onSelectFolder(
        f.system_key === "inbox" ? null : f.id,
        f.system_key
      )}
      className={cn(
        "flex items-center gap-2 py-1.5 rounded-md text-sm transition-colors w-full text-left",
        indent ? "pl-7 pr-3" : "px-3",
        isSelected(f)
          ? "bg-accent text-accent-foreground font-medium"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      )}
    >
      <span className="shrink-0 text-muted-foreground">
        {f.icon && ICON_MAP[f.icon] ? ICON_MAP[f.icon] : <Folder className="h-3.5 w-3.5" />}
      </span>
      <span className="flex-1 truncate">{f.name}</span>
      {f.system_key === "inbox" && canSeeAllMail && (autoHandledToday ?? 0) > 0 && (
        <span
          className="h-4 px-1 text-[9px] font-medium rounded bg-sky-100 dark:bg-sky-950/40 text-sky-700 dark:text-sky-400 inline-flex items-center"
          title={`${autoHandledToday} email${autoHandledToday === 1 ? '' : 's'} auto-handled in last 24h. Click All Mail to review.`}
        >
          +{autoHandledToday}
        </span>
      )}
      {f.unread_count > 0 && (
        <Badge variant="default" className="h-5 min-w-[20px] px-1.5 text-[10px] font-semibold">
          {f.unread_count}
        </Badge>
      )}
    </button>
  );

  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      {/* Compose — top of the inbox sidebar, above folders. Gmail pattern. */}
      <Button
        className="w-full gap-2 mb-2 shadow-sm"
        size="sm"
        onClick={() => openCompose()}
      >
        <PenSquare className="h-3.5 w-3.5" />
        Compose
      </Button>

      {/* Inbox + custom folders nested underneath */}
      {inboxFolder && renderFolder(inboxFolder)}
      {customFolders.map((f) => renderFolder(f, true))}
      <button
        onClick={() => setShowCreate(true)}
        className="flex items-center gap-2 pl-7 pr-3 py-1 rounded-md text-xs text-muted-foreground/60 hover:bg-muted hover:text-muted-foreground transition-colors w-full text-left"
      >
        <Plus className="h-3 w-3" />
        <span>New Folder</span>
      </button>

      {/* Separator */}
      <div className="h-px bg-border my-1.5" />

      {/* System folders: Sent, Spam */}
      {systemFolders.map((f) => renderFolder(f))}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-xs">
          <DialogHeader>
            <DialogTitle>New Folder</DialogTitle>
          </DialogHeader>
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Folder name"
            onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
            autoFocus
          />
          <DialogFooter>
            <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button size="sm" onClick={handleCreate} disabled={creating || !newName.trim()}>
              {creating && <Loader2 className="h-3 w-3 animate-spin mr-1" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
