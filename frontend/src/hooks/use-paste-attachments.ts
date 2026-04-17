"use client";

import { useCallback } from "react";
import { resizeImage } from "@/lib/image-utils";
import { api } from "@/lib/api";
import type { UploadedAttachment } from "@/components/ui/attachment-picker";

const BLOCKED_EXTENSIONS = new Set([
  ".exe", ".bat", ".cmd", ".sh", ".com", ".msi", ".scr", ".ps1", ".vbs", ".js", ".wsf",
  ".svg", ".html", ".htm", ".xhtml",
]);
const MAX_SIZE = 10 * 1024 * 1024;

/**
 * Returns an onPaste handler that extracts files from clipboard
 * and uploads them via the attachments API.
 */
export function usePasteAttachments({
  attachments,
  onAttachmentsChange,
  sourceType,
  maxFiles = 5,
}: {
  attachments: UploadedAttachment[];
  onAttachmentsChange: (attachments: UploadedAttachment[]) => void;
  sourceType: "internal_message" | "agent_message";
  maxFiles?: number;
}) {
  const onPaste = useCallback(
    async (e: React.ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;

      const files: File[] = [];
      for (const item of Array.from(items)) {
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      }
      if (files.length === 0) return;

      // Don't prevent default for text paste (only intercept file paste)
      e.preventDefault();

      const remaining = maxFiles - attachments.length;
      if (remaining <= 0) return;

      const toUpload = files.slice(0, remaining);
      const results: UploadedAttachment[] = [];

      for (const file of toUpload) {
        const ext = file.name.includes(".")
          ? "." + file.name.split(".").pop()!.toLowerCase()
          : "";
        if (BLOCKED_EXTENSIONS.has(ext)) continue;
        if (!file.type.startsWith("image/") && file.size > MAX_SIZE) continue;

        let blob: Blob = file;
        if (file.type.startsWith("image/")) {
          blob = await resizeImage(file, 1600, 0.85);
        }

        const fd = new FormData();
        fd.append("file", blob, file.name || "pasted-image.png");
        fd.append("source_type", sourceType);

        try {
          const att = await api.upload<UploadedAttachment>(
            "/v1/attachments/upload",
            fd
          );
          results.push(att);
        } catch {
          // silently skip failed uploads
        }
      }

      if (results.length) {
        onAttachmentsChange([...attachments, ...results]);
      }
    },
    [attachments, onAttachmentsChange, sourceType, maxFiles]
  );

  return onPaste;
}
