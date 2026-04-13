"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { InboxFolderItem } from "./inbox-folder-sidebar";

interface Props {
  selectedFolderId: string | null;
  onSelectFolder: (folderId: string | null, systemKey: string | null) => void;
}

export function InboxFolderPills({ selectedFolderId, onSelectFolder }: Props) {
  const [folders, setFolders] = useState<InboxFolderItem[]>([]);

  useEffect(() => {
    api.get<{ folders: InboxFolderItem[] }>("/v1/inbox-folders")
      .then((d) => setFolders(d.folders))
      .catch(() => {});
  }, []);

  if (folders.length === 0) return null;

  const isSelected = (f: InboxFolderItem) => {
    if (f.system_key === "inbox" && selectedFolderId === null) return true;
    return f.id === selectedFolderId;
  };

  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1 sm:hidden">
      {folders.map((f) => (
        <button
          key={f.id}
          onClick={() => onSelectFolder(
            f.system_key === "inbox" ? null : f.id,
            f.system_key
          )}
          className={cn(
            "shrink-0 px-3 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap",
            isSelected(f)
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground hover:bg-muted/80"
          )}
        >
          {f.name}
          {f.unread_count > 0 && (
            <span className="ml-1.5 bg-background/20 px-1 rounded-full text-[10px]">
              {f.unread_count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
