"use client";

import { useState, useRef } from "react";
import { Paperclip, X, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { resizeImage } from "@/lib/image-utils";
import { api, getBackendOrigin } from "@/lib/api";

export interface UploadedAttachment {
  id: string;
  filename: string;
  url: string;
  mime_type: string;
  file_size: number;
}

interface AttachmentPickerProps {
  attachments: UploadedAttachment[];
  onAttachmentsChange: (attachments: UploadedAttachment[]) => void;
  sourceType: "internal_message" | "agent_message";
  maxFiles?: number;
}

const BLOCKED_EXTENSIONS = new Set([
  ".exe", ".bat", ".cmd", ".sh", ".com", ".msi", ".scr", ".ps1", ".vbs", ".js", ".wsf",
  ".svg", ".html", ".htm", ".xhtml",
]);
const MAX_SIZE = 10 * 1024 * 1024;

export function AttachmentPicker({
  attachments,
  onAttachmentsChange,
  sourceType,
  maxFiles = 5,
}: AttachmentPickerProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    setError(null);

    const remaining = maxFiles - attachments.length;
    if (remaining <= 0) {
      setError(`Max ${maxFiles} attachments`);
      return;
    }

    const toUpload = Array.from(files).slice(0, remaining);
    setUploading(true);

    try {
      const results: UploadedAttachment[] = [];
      for (const file of toUpload) {
        const ext = file.name.includes(".") ? "." + file.name.split(".").pop()!.toLowerCase() : "";
        if (BLOCKED_EXTENSIONS.has(ext)) {
          setError("Executable files are not allowed");
          continue;
        }
        if (!file.type.startsWith("image/") && file.size > MAX_SIZE) {
          setError("File too large (max 10MB)");
          continue;
        }

        let blob: Blob = file;
        if (file.type.startsWith("image/")) {
          blob = await resizeImage(file, 1600, 0.85);
        }

        const fd = new FormData();
        fd.append("file", blob, file.name);
        fd.append("source_type", sourceType);

        const att = await api.upload<UploadedAttachment>(
          "/v1/attachments/upload",
          fd
        );
        results.push(att);
      }
      if (results.length) {
        onAttachmentsChange([...attachments, ...results]);
      }
    } catch {
      setError("Upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function remove(id: string) {
    onAttachmentsChange(attachments.filter((a) => a.id !== id));
  }

  return (
    <div className="space-y-2">
      <input
        ref={inputRef}
        type="file"
        accept="*/*"
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={uploading || attachments.length >= maxFiles}
          onClick={() => inputRef.current?.click()}
          className="text-muted-foreground"
        >
          {uploading ? (
            <Loader2 className="h-4 w-4 animate-spin mr-1" />
          ) : (
            <Paperclip className="h-4 w-4 mr-1" />
          )}
          Attach
        </Button>
        {error && (
          <span className="text-xs text-destructive">{error}</span>
        )}
      </div>

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {attachments.map((att) => (
            <div
              key={att.id}
              className="flex items-center gap-1.5 bg-muted/50 rounded px-2 py-1 text-xs"
            >
              {att.mime_type.startsWith("image/") ? (
                <img
                  src={`${getBackendOrigin()}${att.url}`}
                  alt={att.filename}
                  className="h-8 w-8 rounded object-cover"
                />
              ) : (
                <FileText className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="max-w-[120px] truncate">{att.filename}</span>
              <button
                type="button"
                onClick={() => remove(att.id)}
                className="text-muted-foreground hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
