"use client";

import { useDeepBlue } from "./deepblue-provider";
import { Sparkles } from "lucide-react";

export function DeepBlueTrigger() {
  const { isOpen, toggleDeepBlue } = useDeepBlue();

  if (isOpen) return null;

  return (
    <button
      onClick={toggleDeepBlue}
      className="fixed bottom-20 right-4 z-[70] h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-lg hover:shadow-xl transition-all flex items-center justify-center sm:bottom-6 sm:right-6 sm:h-11 sm:w-11 active:scale-95"
      style={{ touchAction: "manipulation", WebkitTapHighlightColor: "transparent" }}
      title="Ask DeepBlue"
    >
      <Sparkles className="h-5 w-5" />
    </button>
  );
}
