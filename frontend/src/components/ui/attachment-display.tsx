"use client";

import { FileText, Download, FileImage, Film, File, Table, FileArchive } from "lucide-react";
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

function getFileExtension(filename: string): string {
  const parts = filename.split(".");
  return parts.length > 1 ? parts[parts.length - 1].toUpperCase() : "FILE";
}

function getFileTypeInfo(mime: string, filename: string): {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  bgColor: string;
  textColor: string;
} {
  const ext = getFileExtension(filename);
  if (mime.startsWith("image/")) return { icon: FileImage, label: ext, bgColor: "bg-emerald-100 dark:bg-emerald-950/40", textColor: "text-emerald-700 dark:text-emerald-400" };
  if (mime.startsWith("video/")) return { icon: Film, label: ext, bgColor: "bg-purple-100 dark:bg-purple-950/40", textColor: "text-purple-700 dark:text-purple-400" };
  if (mime === "application/pdf" || ext === "PDF") return { icon: FileText, label: "PDF", bgColor: "bg-red-100 dark:bg-red-950/40", textColor: "text-red-700 dark:text-red-400" };
  if (ext === "DOC" || ext === "DOCX" || mime.includes("word")) return { icon: FileText, label: ext, bgColor: "bg-blue-100 dark:bg-blue-950/40", textColor: "text-blue-700 dark:text-blue-400" };
  if (ext === "XLS" || ext === "XLSX" || ext === "CSV" || mime.includes("sheet") || mime.includes("csv")) return { icon: Table, label: ext, bgColor: "bg-green-100 dark:bg-green-950/40", textColor: "text-green-700 dark:text-green-400" };
  if (ext === "ZIP" || ext === "RAR" || ext === "7Z" || ext === "TAR" || mime.includes("zip")) return { icon: FileArchive, label: ext, bgColor: "bg-amber-100 dark:bg-amber-950/40", textColor: "text-amber-700 dark:text-amber-400" };
  return { icon: File, label: ext, bgColor: "bg-muted", textColor: "text-muted-foreground" };
}

export function AttachmentDisplay({ attachments }: AttachmentDisplayProps) {
  if (!attachments?.length) return null;

  const backendOrigin = getBackendOrigin();
  const images = attachments.filter((a) => a.mime_type.startsWith("image/"));
  const files = attachments.filter((a) => !a.mime_type.startsWith("image/"));

  return (
    <div className="space-y-2 mt-2">
      {/* Image grid */}
      {images.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {images.map((att) => {
            const fullUrl = `${backendOrigin}${att.url}`;
            return (
              <a
                key={att.id}
                href={fullUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="group relative block aspect-square rounded-lg border overflow-hidden bg-muted hover:ring-2 hover:ring-primary transition-all"
              >
                <img
                  src={fullUrl}
                  alt={att.filename}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                />
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <p className="text-[10px] text-white truncate">{att.filename}</p>
                  <p className="text-[9px] text-white/70">{formatSize(att.file_size)}</p>
                </div>
              </a>
            );
          })}
        </div>
      )}

      {/* File chips */}
      {files.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {files.map((att) => {
            const fullUrl = `${backendOrigin}${att.url}`;
            const { icon: Icon, label, bgColor, textColor } = getFileTypeInfo(att.mime_type, att.filename);
            return (
              <a
                key={att.id}
                href={fullUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center gap-2 rounded-lg border bg-background hover:bg-muted/50 transition-colors p-2 max-w-[260px]"
              >
                <div className={`flex items-center justify-center w-10 h-10 rounded ${bgColor} ${textColor} shrink-0`}>
                  <Icon className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate">{att.filename}</p>
                  <p className="text-[10px] text-muted-foreground">
                    <span className={`font-medium ${textColor}`}>{label}</span>
                    <span className="mx-1">·</span>
                    {formatSize(att.file_size)}
                  </p>
                </div>
                <Download className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
