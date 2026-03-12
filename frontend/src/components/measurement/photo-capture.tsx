"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { Camera, X } from "lucide-react";

interface PhotoFile {
  file: File;
  preview: string;
  type: "overview" | "depth";
}

interface PhotoCaptureProps {
  label: string;
  photoType: "overview" | "depth";
  photos: PhotoFile[];
  onAdd: (photo: PhotoFile) => void;
  onRemove: (index: number) => void;
}

export function PhotoCapture({
  label,
  photoType,
  photos,
  onAdd,
  onRemove,
}: PhotoCaptureProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onAdd({
      file,
      preview: URL.createObjectURL(file),
      type: photoType,
    });
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium">{label}</label>
        <span className="text-xs text-muted-foreground">
          {photos.length} photo{photos.length !== 1 ? "s" : ""}
        </span>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFile}
        className="hidden"
      />

      <Button
        type="button"
        variant="outline"
        className="w-full h-16 sm:h-20 border-dashed text-base"
        onClick={() => inputRef.current?.click()}
      >
        <Camera className="h-6 w-6 mr-2" />
        Take Photo
      </Button>

      {photos.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {photos.map((photo, i) => (
            <div key={i} className="relative">
              <img
                src={photo.preview}
                alt={`${photoType} ${i + 1}`}
                className="w-full h-24 sm:h-20 object-cover rounded-md border"
              />
              <button
                type="button"
                onClick={() => onRemove(i)}
                className="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full p-1 shadow-sm"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export type { PhotoFile };
