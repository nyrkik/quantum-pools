"use client";

import { Button } from "@/components/ui/button";
import { Loader2, Plus, Search, Users, X } from "lucide-react";
import { ConversationRow } from "@/components/deepblue/conversation-row";
import type { ConversationListItem } from "@/components/deepblue/conversation-row";

interface DeepBlueSidebarProps {
  conversations: ConversationListItem[];
  loadingList: boolean;
  scope: "mine" | "shared";
  onScopeChange: (scope: "mine" | "shared") => void;
  search: string;
  onSearchChange: (v: string) => void;
  activeId: string | null;
  currentUserId: string;
  pendingDelete: string | null;
  sidebarOpen: boolean;
  onSidebarClose: () => void;
  onStartNew: () => void;
  onSelectConversation: (id: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onToggleShare: (id: string, visibility: string) => void;
  onDeleteStart: (id: string) => void;
  onDeleteConfirm: (id: string) => void;
  onDeleteCancel: () => void;
}

export function DeepBlueSidebar({
  conversations,
  loadingList,
  scope,
  onScopeChange,
  search,
  onSearchChange,
  activeId,
  currentUserId,
  pendingDelete,
  sidebarOpen,
  onSidebarClose,
  onStartNew,
  onSelectConversation,
  onTogglePin,
  onToggleShare,
  onDeleteStart,
  onDeleteConfirm,
  onDeleteCancel,
}: DeepBlueSidebarProps) {
  const filtered = conversations.filter((c) =>
    !search.trim() || (c.title || "").toLowerCase().includes(search.toLowerCase())
  );

  const pinnedChats = filtered.filter((c) => c.pinned);
  const unpinnedChats = filtered.filter((c) => !c.pinned);

  return (
    <>
      <div className={`
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} sm:translate-x-0
        fixed sm:static top-14 sm:top-0 bottom-0 left-0 z-40 w-72 bg-background border-r flex flex-col
        transition-transform duration-200
      `}>
        <div className="flex items-center justify-between p-3 border-b">
          <span className="text-sm font-semibold">Chats</span>
          <Button size="sm" variant="ghost" className="sm:hidden" onClick={onSidebarClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="p-2 space-y-2">
          <Button className="w-full justify-start" size="sm" onClick={onStartNew}>
            <Plus className="h-3.5 w-3.5 mr-1.5" /> New chat
          </Button>
          <div className="relative">
            <Search className="h-3 w-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search..."
              className="w-full h-8 pl-7 pr-2 text-xs rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
          </div>
          <div className="flex gap-1">
            <Button size="sm" variant={scope === "mine" ? "default" : "ghost"} className="h-6 text-[10px] flex-1" onClick={() => onScopeChange("mine")}>
              Mine
            </Button>
            <Button size="sm" variant={scope === "shared" ? "default" : "ghost"} className="h-6 text-[10px] flex-1" onClick={() => onScopeChange("shared")}>
              <Users className="h-2.5 w-2.5 mr-0.5" /> Shared
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {loadingList ? (
            <div className="flex justify-center py-6"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
          ) : filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-6">
              {scope === "mine" ? "No conversations yet." : "Nothing shared with the team."}
            </p>
          ) : (
            <>
              {pinnedChats.length > 0 && (
                <>
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground px-2 pt-2 pb-1">Pinned</p>
                  {pinnedChats.map((c) => (
                    <ConversationRow
                      key={c.id}
                      conv={c}
                      isActive={c.id === activeId}
                      showActions={c.user_id === currentUserId}
                      pendingDelete={pendingDelete}
                      onSelect={() => onSelectConversation(c.id)}
                      onPin={() => onTogglePin(c.id, c.pinned)}
                      onShare={() => onToggleShare(c.id, c.visibility)}
                      onDeleteStart={() => onDeleteStart(c.id)}
                      onDeleteConfirm={() => onDeleteConfirm(c.id)}
                      onDeleteCancel={onDeleteCancel}
                    />
                  ))}
                </>
              )}
              {unpinnedChats.length > 0 && (
                <>
                  {pinnedChats.length > 0 && (
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground px-2 pt-2 pb-1">Recent</p>
                  )}
                  {unpinnedChats.map((c) => (
                    <ConversationRow
                      key={c.id}
                      conv={c}
                      isActive={c.id === activeId}
                      showActions={c.user_id === currentUserId}
                      pendingDelete={pendingDelete}
                      onSelect={() => onSelectConversation(c.id)}
                      onPin={() => onTogglePin(c.id, c.pinned)}
                      onShare={() => onToggleShare(c.id, c.visibility)}
                      onDeleteStart={() => onDeleteStart(c.id)}
                      onDeleteConfirm={() => onDeleteConfirm(c.id)}
                      onDeleteCancel={onDeleteCancel}
                    />
                  ))}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Backdrop for mobile sidebar */}
      {sidebarOpen && (
        <div className="fixed inset-x-0 bottom-0 top-14 bg-black/30 z-30 sm:hidden" onClick={onSidebarClose} />
      )}
    </>
  );
}
