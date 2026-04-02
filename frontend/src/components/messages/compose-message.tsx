"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody, OverlayFooter } from "@/components/ui/overlay";
import { toast } from "sonner";
import { Loader2, X } from "lucide-react";
import { useTeamMembersFull } from "@/hooks/use-team-members";
import { AttachmentPicker, type UploadedAttachment } from "@/components/ui/attachment-picker";

interface ComposeMessageProps {
  open: boolean;
  onClose: () => void;
  onSent: () => void;
  defaultCustomerId?: string;
  defaultActionId?: string;
  defaultCaseId?: string;
}

export function ComposeMessage({ open, onClose, onSent, defaultCustomerId, defaultActionId, defaultCaseId }: ComposeMessageProps) {
  const team = useTeamMembersFull();
  const [selectedUsers, setSelectedUsers] = useState<{ id: string; name: string }[]>([]);
  const [message, setMessage] = useState("");
  const [subject, setSubject] = useState("");
  const [priority, setPriority] = useState("normal");
  const [sending, setSending] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [attachments, setAttachments] = useState<UploadedAttachment[]>([]);

  const reset = () => {
    setSelectedUsers([]);
    setMessage("");
    setSubject("");
    setPriority("normal");
    setSearchQuery("");
    setAttachments([]);
  };

  const addUser = (userId: string, name: string) => {
    if (!selectedUsers.find((u) => u.id === userId)) {
      setSelectedUsers([...selectedUsers, { id: userId, name }]);
    }
    setSearchQuery("");
    setShowDropdown(false);
  };

  const removeUser = (userId: string) => {
    setSelectedUsers(selectedUsers.filter((u) => u.id !== userId));
  };

  const filteredTeam = team.filter(
    (m) =>
      !selectedUsers.find((u) => u.id === m.user_id) &&
      `${m.first_name} ${m.last_name}`.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleSend = async () => {
    if (selectedUsers.length === 0 || !message.trim()) return;
    setSending(true);
    try {
      await api.post("/v1/messages", {
        to_user_ids: selectedUsers.map((u) => u.id),
        message: message.trim(),
        subject: subject.trim() || null,
        priority,
        customer_id: defaultCustomerId || null,
        action_id: defaultActionId || null,
        case_id: defaultCaseId || null,
        attachment_ids: attachments.length ? attachments.map((a) => a.id) : undefined,
      });
      toast.success("Message sent");
      reset();
      onSent();
    } catch {
      toast.error("Failed to send");
    } finally {
      setSending(false);
    }
  };

  return (
    <Overlay open={open} onOpenChange={(o) => { if (!o) { onClose(); reset(); } }}>
      <OverlayContent className="max-w-md">
        <OverlayHeader>
          <OverlayTitle>New Message</OverlayTitle>
        </OverlayHeader>
        <OverlayBody className="space-y-3">
          {/* Multi-select recipients */}
          <div className="space-y-1">
            <Label className="text-xs">To</Label>
            <div className="border rounded-md p-1.5 min-h-[2.25rem] flex flex-wrap gap-1 items-center">
              {selectedUsers.map((u) => (
                <Badge key={u.id} variant="secondary" className="text-xs gap-1 pr-1">
                  {u.name}
                  <button onClick={() => removeUser(u.id)} className="hover:text-destructive">
                    <X className="h-2.5 w-2.5" />
                  </button>
                </Badge>
              ))}
              <div className="relative flex-1 min-w-[100px]">
                <Input
                  value={searchQuery}
                  onChange={(e) => { setSearchQuery(e.target.value); setShowDropdown(true); }}
                  onFocus={() => setShowDropdown(true)}
                  placeholder={selectedUsers.length === 0 ? "Search team..." : "Add more..."}
                  className="border-0 h-7 text-sm p-0 pl-1 shadow-none focus-visible:ring-0"
                />
                {showDropdown && filteredTeam.length > 0 && (
                  <div className="absolute top-full left-0 mt-1 w-48 bg-background border rounded-md shadow-lg z-10 py-1 max-h-32 overflow-y-auto">
                    {filteredTeam.map((m) => (
                      <button
                        key={m.user_id}
                        className="w-full text-left px-3 py-1.5 text-sm hover:bg-muted transition-colors"
                        onClick={() => addUser(m.user_id, `${m.first_name} ${m.last_name}`.trim())}
                      >
                        {m.first_name} {m.last_name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Subject (optional)</Label>
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. Call Mrs. Johnson"
              className="text-sm"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Message</Label>
            <Textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="What do you need?"
              className="text-sm resize-none"
              rows={3}
              autoFocus
            />
          </div>

          <div className="flex gap-1 bg-muted p-0.5 rounded-md w-fit">
            <button
              onClick={() => setPriority("normal")}
              className={`px-3 py-1 text-xs rounded transition-colors ${priority === "normal" ? "bg-background shadow-sm font-medium" : "text-muted-foreground"}`}
            >
              Normal
            </button>
            <button
              onClick={() => setPriority("urgent")}
              className={`px-3 py-1 text-xs rounded transition-colors ${priority === "urgent" ? "bg-amber-100 shadow-sm font-medium text-amber-700" : "text-muted-foreground"}`}
            >
              Urgent
            </button>
          </div>

          <AttachmentPicker
            attachments={attachments}
            onAttachmentsChange={setAttachments}
            sourceType="internal_message"
          />
        </OverlayBody>
        <OverlayFooter>
          <Button className="flex-1" onClick={handleSend} disabled={selectedUsers.length === 0 || !message.trim() || sending}>
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Send"}
          </Button>
          <Button variant="ghost" onClick={() => { onClose(); reset(); }}>Cancel</Button>
        </OverlayFooter>
      </OverlayContent>
    </Overlay>
  );
}
