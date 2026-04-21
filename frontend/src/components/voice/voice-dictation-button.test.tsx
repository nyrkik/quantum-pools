/**
 * VoiceDictationButton — browser-speech dictation button.
 *
 * Covers the four acceptance criteria from docs/voice-integration-plan.md §3.4:
 *   - Feature detect: render nothing when Web Speech API is missing.
 *   - onTranscript fires with final phrases.
 *   - onInterim fires with interim phrases.
 *   - Permission denied sets error state without crashing.
 * Plus the telemetry contract — `voice.dictated` emits on stop with
 * the documented payload + no transcript content.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, cleanup } from "@testing-library/react";

const emitSpy = vi.fn();
vi.mock("@/lib/events", () => ({
  events: { emit: (type: string, input: unknown) => emitSpy(type, input) },
}));

import { VoiceDictationButton } from "./voice-dictation-button";

// ---------------------------------------------------------------------------
// Web Speech API stub
// ---------------------------------------------------------------------------

type RecognitionStub = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((ev: unknown) => void) | null;
  onerror: ((ev: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  // test hooks:
  _emitFinal: (text: string) => void;
  _emitInterim: (text: string) => void;
  _emitError: (code: string) => void;
};

function makeStub(): RecognitionStub {
  const stub = {
    lang: "en-US",
    continuous: true,
    interimResults: true,
    onresult: null as ((ev: unknown) => void) | null,
    onerror: null as ((ev: { error: string }) => void) | null,
    onend: null as (() => void) | null,
    start: vi.fn(),
    stop: vi.fn(function (this: RecognitionStub) {
      if (this.onend) this.onend();
    }),
    _emitFinal(text: string) {
      this.onresult?.({
        results: [{ isFinal: true, 0: { transcript: text } }],
      });
    },
    _emitInterim(text: string) {
      this.onresult?.({
        results: [{ isFinal: false, 0: { transcript: text } }],
      });
    },
    _emitError(code: string) {
      this.onerror?.({ error: code });
    },
  };
  // bind `this` in methods that use it
  stub.stop = stub.stop.bind(stub);
  stub._emitFinal = stub._emitFinal.bind(stub);
  stub._emitInterim = stub._emitInterim.bind(stub);
  stub._emitError = stub._emitError.bind(stub);
  return stub;
}

let lastStub: RecognitionStub | null = null;

function installSpeechApi() {
  (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition =
    vi.fn(function () {
      lastStub = makeStub();
      return lastStub;
    });
}

function removeSpeechApi() {
  delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition;
  delete (window as unknown as { webkitSpeechRecognition?: unknown })
    .webkitSpeechRecognition;
}

beforeEach(() => {
  emitSpy.mockReset();
  lastStub = null;
  installSpeechApi();
});

afterEach(() => {
  cleanup();
  removeSpeechApi();
});

describe("VoiceDictationButton", () => {
  it("renders null when the browser has no Web Speech API", () => {
    removeSpeechApi();
    const { container } = render(
      <VoiceDictationButton onTranscript={vi.fn()} surface="deepblue_chat" />,
    );
    // Effect runs on mount and flips supported=false → component
    // returns null. Placeholder may still be in the DOM from the
    // first render — find a real button.
    expect(screen.queryByRole("button", { name: /dictat/i })).toBeNull();
    expect(container.querySelector("button[aria-label]")).toBeNull();
  });

  it("click → start → onTranscript fires with final phrase", async () => {
    const onTranscript = vi.fn();
    render(
      <VoiceDictationButton
        onTranscript={onTranscript}
        surface="deepblue_chat"
      />,
    );
    const btn = await screen.findByRole("button", { name: /Start voice/ });
    act(() => btn.click());

    // Recognition was constructed and started.
    expect(lastStub).not.toBeNull();
    expect(lastStub!.start).toHaveBeenCalled();

    act(() => lastStub!._emitFinal("pump pressure is high"));
    expect(onTranscript).toHaveBeenCalledWith("pump pressure is high");
  });

  it("onInterim fires with interim phrases", async () => {
    const onInterim = vi.fn();
    render(
      <VoiceDictationButton
        onTranscript={vi.fn()}
        onInterim={onInterim}
        surface="email_reply"
      />,
    );
    const btn = await screen.findByRole("button", { name: /Start voice/ });
    act(() => btn.click());

    act(() => lastStub!._emitInterim("checking the"));
    expect(onInterim).toHaveBeenCalledWith("checking the");
  });

  it("permission denied sets error state without throwing", async () => {
    render(
      <VoiceDictationButton
        onTranscript={vi.fn()}
        surface="job_notes"
      />,
    );
    const btn = await screen.findByRole("button", { name: /Start voice/ });
    act(() => btn.click());

    act(() => lastStub!._emitError("not-allowed"));
    // Button still mounted; title flips to the hint.
    const btnAfter = screen.getByRole("button");
    expect(btnAfter.getAttribute("title") || "").toMatch(
      /Microphone blocked/,
    );
  });

  it("emits voice.dictated with metadata only (no transcript content) on stop", async () => {
    render(
      <VoiceDictationButton
        onTranscript={vi.fn()}
        surface="deepblue_chat"
      />,
    );
    const btn = await screen.findByRole("button", { name: /Start voice/ });
    act(() => btn.click());
    act(() => lastStub!._emitFinal("schedule a callback for Kim"));

    // Click again to stop — stub.stop() synchronously fires onend.
    act(() => screen.getByRole("button").click());

    const dictated = emitSpy.mock.calls.find(([t]) => t === "voice.dictated");
    expect(dictated).toBeTruthy();
    const payload = (dictated![1] as { payload: Record<string, unknown> })
      .payload;
    expect(payload.surface).toBe("deepblue_chat");
    expect(payload.language).toBe("en-US");
    expect(typeof payload.duration_ms).toBe("number");
    expect(payload.char_count).toBe("schedule a callback for Kim".length);
    // Privacy guard — no transcript content in the event.
    expect(JSON.stringify(payload)).not.toContain("schedule a callback");
    expect(JSON.stringify(payload)).not.toContain("Kim");
  });
});
