"use client";

import { FileText, Download } from "lucide-react";
import { getBackendOrigin } from "@/lib/api";

export interface AttachmentInfo {
  id: string;
  filename: string;
  url: string;
  mime_type: string;
  file_size: number;
}

interface AttachmentDisplayProps {
  attachments: AttachmentInfo[];
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function AttachmentDisplay({ attachments }: AttachmentDisplayProps) {
  if (!attachments?.length) return null;

  const backendOrigin = getBackendOrigin();

  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {attachments.map((att) => {
        const fullUrl = `${backendOrigin}${att.url}`;
        const isImage = att.mime_type.startsWith("image/");

        if (isImage) {
          return (
            <a
              key={att.id}
              href={fullUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="block"
            >
              <img
                src={fullUrl}
                alt={att.filename}
                className="h-16 w-16 rounded object-cover border hover:opacity-80 transition-opacity"
              />
            </a>
          );
        }

        return (
          <a
            key={att.id}
            href={fullUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 bg-muted/50 rounded px-2 py-1.5 text-xs hover:bg-muted transition-colors"
          >
            <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <span className="max-w-[140px] truncate">{att.filename}</span>
            <span className="text-muted-foreground">{formatSize(att.file_size)}</span>
            <Download className="h-3 w-3 text-muted-foreground" />
          </a>
        );
      })}
    </div>
  );
}
