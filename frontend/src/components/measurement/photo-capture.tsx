"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Camera, X, Loader2 } from "lucide-react";

const MAX_DIMENSION = 1600;
const JPEG_QUALITY = 0.85;

function resizeImage(file: File): Promise<File> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      if (width <= MAX_DIMENSION && height <= MAX_DIMENSION) {
        URL.revokeObjectURL(img.src);
        resolve(file);
        return;
      }
      const scale = MAX_DIMENSION / Math.max(width, height);
      width = Math.round(width * scale);
      height = Math.round(height * scale);
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(img.src);
      canvas.toBlob(
        (blob) => {
          if (!blob) return reject(new Error("Resize failed"));
          resolve(new File([blob], file.name.replace(/\.\w+$/, ".jpg"), { type: "image/jpeg" }));
        },
        "image/jpeg",
        JPEG_QUALITY
      );
    };
    img.onerror = () => reject(new Error("Failed to load image"));
    img.src = URL.createObjectURL(file);
  });
}

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
  const [resizing, setResizing] = useState(false);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setResizing(true);
    try {
      const resized = await resizeImage(file);
      onAdd({
        file: resized,
        preview: URL.createObjectURL(resized),
        type: photoType,
      });
    } finally {
      setResizing(false);
      if (inputRef.current) inputRef.current.value = "";
    }
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
        disabled={resizing}
      >
        {resizing ? (
          <>
            <Loader2 className="h-6 w-6 mr-2 animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <Camera className="h-6 w-6 mr-2" />
            Take Photo
          </>
        )}
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

export { resizeImage };
export type { PhotoFile };
