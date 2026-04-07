"use client";

import { Button } from "@/components/ui/button";
import { Pin, PinOff, Trash2, Users, Lock, X, Check } from "lucide-react";

export interface ConversationListItem {
  id: string;
  title: string;
  user_id: string;
  visibility: string;
  pinned: boolean;
  message_count: number;
  updated_at: string;
}

interface ConversationRowProps {
  conv: ConversationListItem;
  isActive: boolean;
  showActions: boolean;
  pendingDelete: string | null;
  onSelect: () => void;
  onPin: () => void;
  onShare: () => void;
  onDeleteStart: () => void;
  onDeleteConfirm: () => void;
  onDeleteCancel: () => void;
}

export function ConversationRow({
  conv, isActive, showActions, pendingDelete, onSelect, onPin, onShare,
  onDeleteStart, onDeleteConfirm, onDeleteCancel,
}: ConversationRowProps) {
  return (
    <div className={`group rounded-md p-1.5 ${isActive ? "bg-primary/10" : "hover:bg-muted/50"}`}>
      <button className="w-full text-left" onClick={onSelect}>
        <div className="flex items-center gap-1.5">
          {conv.pinned && <Pin className="h-2.5 w-2.5 text-amber-500 shrink-0" />}
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate">{conv.title || "Untitled"}</p>
            <p className="text-[10px] text-muted-foreground">
              {conv.message_count} · {new Date(conv.updated_at).toLocaleDateString()}
              {conv.visibility === "shared" && " · Shared"}
            </p>
          </div>
        </div>
      </button>
      {showActions && (
        <div className="flex items-center gap-0.5 mt-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={(e) => { e.stopPropagation(); onPin(); }}
            title={conv.pinned ? "Unpin conversation" : "Pin conversation"}
          >
            {conv.pinned ? (
              <Pin className="h-2.5 w-2.5 text-amber-500 fill-amber-500" />
            ) : (
              <PinOff className="h-2.5 w-2.5 text-muted-foreground" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={(e) => { e.stopPropagation(); onShare(); }}
            title={conv.visibility === "shared" ? "Shared with team — click to make private" : "Private — click to share with team"}
          >
            {conv.visibility === "shared" ? (
              <Users className="h-2.5 w-2.5 text-primary" />
            ) : (
              <Lock className="h-2.5 w-2.5 text-muted-foreground" />
            )}
          </Button>
          <div className="flex-1" />
          {pendingDelete === conv.id ? (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={(e) => { e.stopPropagation(); onDeleteCancel(); }}
                title="Cancel delete"
              >
                <X className="h-2.5 w-2.5 text-muted-foreground" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={(e) => { e.stopPropagation(); onDeleteConfirm(); }}
                title="Confirm delete"
              >
                <Check className="h-2.5 w-2.5 text-destructive" />
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={(e) => { e.stopPropagation(); onDeleteStart(); }}
              title="Delete conversation"
            >
              <Trash2 className="h-2.5 w-2.5 text-muted-foreground" />
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
