"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { XIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Overlay — a centered, near-full-height dialog for detail views.
 * Replaces side-sliding Sheets for content overlays.
 * Backdrop click or X closes it.
 */

function Overlay({ ...props }: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root {...props} />;
}

function OverlayContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
      <DialogPrimitive.Content
        className={cn(
          "fixed top-[50%] left-[50%] z-50 translate-x-[-50%] translate-y-[-50%]",
          "w-[calc(100%-1.5rem)] max-w-xl max-h-[90vh]",
          "bg-background border rounded-lg shadow-xl",
          "flex flex-col overflow-hidden",
          "data-[state=open]:animate-in data-[state=closed]:animate-out",
          "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
          "duration-200 outline-none",
          className
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute top-3 right-3 rounded-sm opacity-70 hover:opacity-100 transition-opacity outline-none">
          <XIcon className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

function OverlayHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div className={cn("px-5 pt-4 pb-2 border-b shrink-0", className)} {...props} />
  );
}

function OverlayTitle({ className, ...props }: React.ComponentProps<"h2">) {
  return (
    <h2 className={cn("text-base font-semibold", className)} {...props} />
  );
}

function OverlayBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div className={cn("flex-1 overflow-y-auto px-5 py-3", className)} {...props} />
  );
}

function OverlayFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div className={cn("px-5 py-3 border-t shrink-0 flex gap-2", className)} {...props} />
  );
}

export { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody, OverlayFooter };
