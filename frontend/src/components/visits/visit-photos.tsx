"use client";

import { useState, useRef } from "react";
import { api, getBackendOrigin } from "@/lib/api";
import { resizeImage } from "@/lib/image-utils";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChevronDown, ChevronUp, Camera, Loader2, X, Trash2 } from "lucide-react";
import type { VisitPhoto } from "@/types/visit";

interface VisitPhotosProps {
  visitId: string;
  photos: VisitPhoto[];
  onUpdate: (photos: VisitPhoto[]) => void;
}

const CATEGORIES = [
  { value: "before", label: "Before" },
  { value: "after", label: "After" },
  { value: "equipment", label: "Equipment" },
  { value: "issue", label: "Issue" },
  { value: "debris", label: "Debris" },
];

export function VisitPhotos({ visitId, photos, onUpdate }: VisitPhotosProps) {
  const [open, setOpen] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [category, setCategory] = useState("after");
  const [caption, setCaption] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const resized = await resizeImage(file, 1600);
      const formData = new FormData();
      formData.append("file", resized, file.name);
      formData.append("category", category);
      if (caption.trim()) formData.append("caption", caption.trim());

      const photo = await api.upload<VisitPhoto>(`/v1/visits/${visitId}/photos`, formData);
      onUpdate([...photos, photo]);
      setCaption("");
      toast.success("Photo uploaded");
    } catch {
      toast.error("Failed to upload photo");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (photoId: string) => {
    setDeleting(photoId);
    try {
      await api.delete(`/v1/visits/${visitId}/photos/${photoId}`);
      onUpdate(photos.filter((p) => p.id !== photoId));
      toast.success("Photo deleted");
    } catch {
      toast.error("Failed to delete photo");
    } finally {
      setDeleting(null);
    }
  };

  const photoUrl = (url: string) => {
    if (url.startsWith("http")) return url;
    return `${getBackendOrigin()}${url}`;
  };

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex w-full items-center justify-between rounded-lg bg-muted/60 px-4 py-3 text-left">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">Photos</span>
            {photos.length > 0 && (
              <span className="text-xs text-muted-foreground">{photos.length} photo{photos.length !== 1 ? "s" : ""}</span>
            )}
          </div>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="space-y-3 pt-3">
          {/* Photo grid */}
          {photos.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {photos.map((photo) => (
                <div key={photo.id} className="relative group">
                  <img
                    src={photoUrl(photo.photo_url)}
                    alt={photo.caption || photo.category}
                    className="h-24 w-full rounded-lg border object-cover"
                  />
                  <Badge
                    variant="secondary"
                    className="absolute bottom-1 left-1 text-[10px] px-1 py-0 bg-black/60 text-white border-0"
                  >
                    {photo.category}
                  </Badge>
                  <button
                    onClick={() => handleDelete(photo.id)}
                    disabled={deleting === photo.id}
                    className="absolute top-1 right-1 rounded-full bg-black/60 p-1 text-white opacity-0 group-hover:opacity-100 active:opacity-100 transition-opacity"
                  >
                    {deleting === photo.id ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Trash2 className="h-3 w-3" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Upload controls */}
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1">
              <Input
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                placeholder="Caption (optional)"
                className="h-9 text-xs"
              />
            </div>
            <div>
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                className="hidden"
                onChange={handleCapture}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="h-9"
              >
                {uploading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Camera className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
