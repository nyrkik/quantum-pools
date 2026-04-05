"use client";

import { useState, useRef } from "react";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody, OverlayFooter } from "@/components/ui/overlay";
import { toast } from "sonner";
import { MessageCircleQuestion, Paperclip, Loader2, X } from "lucide-react";
import { getBackendOrigin } from "@/lib/api";
import { resizeImage } from "@/lib/image-utils";

type FeedbackType = "bug" | "feature" | "question";

export function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<FeedbackType>("bug");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [screenshots, setScreenshots] = useState<Blob[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const pathname = usePathname();

  const reset = () => {
    setType("bug");
    setTitle("");
    setDescription("");
    setScreenshots([]);
    setPreviews([]);
    setSubmitted(false);
  };

  const handleClose = () => {
    setOpen(false);
    setTimeout(reset, 300);
  };

  const handleScreenshot = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (const file of Array.from(files)) {
      const resized = await resizeImage(file, 1200);
      setScreenshots((prev) => [...prev, resized]);
      setPreviews((prev) => [...prev, URL.createObjectURL(resized)]);
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  const removeScreenshot = (idx: number) => {
    setScreenshots((prev) => prev.filter((_, i) => i !== idx));
    setPreviews((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async () => {
    if (!title.trim()) return;
    setSubmitting(true);

    try {
      const formData = new FormData();
      formData.append("feedback_type", type);
      formData.append("title", title.trim());
      if (description.trim()) formData.append("description", description.trim());
      formData.append("page_url", pathname);
      formData.append("browser_info", navigator.userAgent);
      for (const file of screenshots) {
        formData.append("screenshots", file);
      }

      const res = await fetch(`/api/v1/feedback`, {
        method: "POST",
        body: formData,
        credentials: "include",
      });

      if (!res.ok) throw new Error("Failed");

      setSubmitted(true);
      toast.success("Feedback submitted — thank you!");
    } catch {
      toast.error("Failed to submit feedback");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-20 left-4 z-[70] h-10 w-10 rounded-full bg-primary text-primary-foreground shadow-lg hover:shadow-xl transition-shadow flex items-center justify-center sm:bottom-6 sm:left-6 sm:h-9 sm:w-auto sm:px-3 sm:rounded-md sm:gap-1.5"
        title="Send Feedback"
      >
        <MessageCircleQuestion className="h-4 w-4" />
        <span className="hidden sm:inline text-xs font-medium">Feedback</span>
      </button>

      <Overlay open={open} onOpenChange={(o) => { if (!o) handleClose(); }}>
        <OverlayContent className="max-w-md">
          <OverlayHeader>
            <OverlayTitle>Send Feedback</OverlayTitle>
          </OverlayHeader>

          {submitted ? (
            <OverlayBody className="text-center py-8 space-y-3">
              <div className="h-12 w-12 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mx-auto">
                <MessageCircleQuestion className="h-6 w-6 text-green-600" />
              </div>
              <p className="text-sm font-medium">Thank you for your feedback!</p>
              <p className="text-xs text-muted-foreground">We'll review it and follow up if needed.</p>
              <Button variant="outline" size="sm" onClick={handleClose}>Close</Button>
            </OverlayBody>
          ) : (
            <>
              <OverlayBody className="space-y-3">
                {/* Type toggle */}
                <div className="flex gap-1 bg-muted p-0.5 rounded-md">
                  {(["bug", "feature", "question"] as FeedbackType[]).map((t) => (
                    <button
                      key={t}
                      onClick={() => setType(t)}
                      className={`flex-1 px-3 py-1.5 text-xs rounded transition-colors capitalize ${
                        type === t ? "bg-background shadow-sm font-medium" : "text-muted-foreground"
                      }`}
                    >
                      {t === "bug" ? "Bug Report" : t === "feature" ? "Feature Request" : "Question"}
                    </button>
                  ))}
                </div>

                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={type === "bug" ? "What went wrong?" : type === "feature" ? "What would you like?" : "What's your question?"}
                  className="text-sm"
                  autoFocus
                />

                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Details (optional)"
                  className="text-sm resize-none"
                  rows={3}
                />

                {/* Screenshots */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={() => fileRef.current?.click()}>
                      <Paperclip className="h-3 w-3" /> Attach File
                    </Button>
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/*,.pdf,.doc,.docx,.txt,.csv,.xlsx"
                      multiple
                      className="hidden"
                      onChange={handleScreenshot}
                    />
                  </div>
                  {previews.length > 0 && (
                    <div className="flex gap-2 flex-wrap">
                      {previews.map((src, i) => (
                        <div key={i} className="relative">
                          <img src={src} alt="" className="h-16 w-16 object-cover rounded-md border" />
                          <button
                            onClick={() => removeScreenshot(i)}
                            className="absolute -top-1 -right-1 h-4 w-4 bg-destructive text-white rounded-full flex items-center justify-center"
                          >
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <p className="text-[10px] text-muted-foreground">
                  Page: {pathname}
                </p>
              </OverlayBody>

              <OverlayFooter>
                <Button className="flex-1" onClick={handleSubmit} disabled={!title.trim() || submitting}>
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit Feedback"}
                </Button>
                <Button variant="ghost" onClick={handleClose}>Cancel</Button>
              </OverlayFooter>
            </>
          )}
        </OverlayContent>
      </Overlay>
    </>
  );
}
