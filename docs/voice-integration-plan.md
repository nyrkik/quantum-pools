# Voice integration — plan

> **Status:** planned 2026-04-20. Phased rollout plan for voice input across QP. **Remove when Phase 3 is shipped or the project is decided against.** Current-state reference (when any phase ships): will be added to `docs/ai-agents-plan.md`.

## 1. Why

Pool techs work in the field. Hands are wet, dirty, holding tools. Typing visit notes + job updates on a phone while kneeling over a pool is where QP loses the most friction points per minute. The same techs routinely pull out their phone to call dispatch — voice is already how they communicate on-site.

DeepBlue's differentiation is conversational AI. Keeping the conversation text-only on a mobile screen wastes that conversational strength. Users already ask if they can "just talk to DeepBlue" — this is FB-29.

DNA rule 6 (less work for the USER, not the engineer): typing 3 sentences of visit notes on a phone is ~30-45 seconds; speaking them is ~8 seconds + 2 seconds of STT latency. 3× - 5× reduction in per-visit friction, compounding across ~60 visits/week/tech.

## 2. What changes

Three phases, each independently valuable. Ship Phase 1 first, only build Phase 2/3 if adoption signal is there.

### Phase 1 — push-to-talk dictation, browser-native (cheap, fast)

Reusable `<VoiceDictationButton>` component wrapping the Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`). Drops into any text input surface. Press mic → speak → press again → transcript appends to the field.

**Infrastructure cost:** $0. Entirely client-side. Chrome + Edge + Safari (iOS 14+, macOS) covered — ~95%+ of tech field phones. Firefox users see no mic button (feature-detected).

**Integration sites (first cut):**
- DeepBlue chat input
- Email reply compose
- Visit notes (once located)
- Job description/notes

**Observability:** emit `voice.dictated` event per successful transcription with `{surface, duration_ms, char_count, language}` — no transcript content, just metadata. Lets us measure adoption without privacy concerns.

### Phase 2 — server-side Whisper (upgrade path)

Triggered when Phase 1 adoption is proven and complaints land on accuracy / Firefox gap / background noise.

Keep the same `<VoiceDictationButton>` UX. Swap the client-side `SpeechRecognition` for: record audio → POST to `/api/v1/voice/transcribe` → backend calls **Groq Whisper v3** (`$0.0007/min`, ~1s latency, excellent accuracy). Result flows back as text, component behaves identically from the outside.

Why Groq over OpenAI Whisper: ~10× cheaper, ~3× faster, same Whisper-v3 model weights. Why Whisper over Deepgram for this phase: batch upload is fine for push-to-talk — streaming is a Phase 3 concern.

### Phase 3 — streaming DeepBlue voice mode (differentiation)

"Hey DeepBlue, when was Madison's pump last replaced?" → streaming STT (Deepgram Nova-2) → Claude streamed → ElevenLabs TTS read aloud. Full hands-free conversational UX for field techs.

This is the demo-reel feature. Only build if Phases 1-2 adoption + customer pull justify it.

## 3. How — Phase 1 implementation

### 3.1 Component API

```tsx
// frontend/src/components/voice/voice-dictation-button.tsx
<VoiceDictationButton
  onTranscript={(finalText) => setValue(v => v + finalText)}
  onInterim={(text) => setLiveTranscript(text)}   // optional — inline preview
  lang="en-US"                                    // optional, defaults en-US
  className="..."
  size="sm" | "md"
  disabled={false}
  surface="deepblue_chat"                         // for telemetry
/>
```

Responsibilities:
- Feature-detect `SpeechRecognition || webkitSpeechRecognition`; render nothing when unsupported (don't confuse Firefox users with a dead button).
- Start/stop on click. Visual state: idle (mic), listening (pulsing red), error (warning icon).
- Request mic permission on first use; handle denial gracefully with a one-line tooltip.
- Append final transcript (calling `onTranscript`). Interim transcripts stream via optional `onInterim`.
- Emit `voice.dictated` platform event on stop via `lib/events` with `{surface, duration_ms, char_count, language}`.

### 3.2 Integration sites

1. **DeepBlue chat input** — `frontend/src/components/deepblue/chat-input.tsx`.
2. **Email reply compose** — `frontend/src/components/inbox/thread-detail-sheet.tsx` and the separate compose component if reachable.
3. **Job description textarea** — `frontend/src/components/jobs/action-detail-content.tsx`.
4. **Visit notes** — wherever the tech-path UI exposes them.

### 3.3 Telemetry event

New taxonomy entry:

| Event | Level | Refs | Payload |
|---|---|---|---|
| `voice.dictated` | user_action | — | `{surface, duration_ms, char_count, language}` |

Payload deliberately has no transcript content — privacy by design. `surface` is an enum (`deepblue_chat`, `email_reply`, `visit_notes`, `job_notes`). We watch adoption with `GROUP BY surface` and attrition with the ratio of dictation-starts to dictation-completes.

### 3.4 Vitest coverage

- Support detection — button hidden when neither `SpeechRecognition` nor `webkitSpeechRecognition` is defined.
- onTranscript fires with the final result when recognition ends.
- onInterim fires while recognition is active.
- Mic-permission-denied sets the error state without blowing up.

### 3.5 DoD (Phase 1)

1. `<VoiceDictationButton>` component in place, browser-support-detected.
2. Wired into DeepBlue chat + email reply + job notes at minimum.
3. `voice.dictated` event emits on successful stop; taxonomy updated in same commit.
4. Vitest covers support-detect, final+interim callbacks, permission-denied.
5. Deployed; smoke-test on desktop Chrome + iOS Safari produces a useful transcript.

## 4. Risks

| Risk | Mitigation |
|---|---|
| Field noise (pool pumps, cars) degrades Web Speech accuracy | Phase 1 ships best-effort. Phase 2 Whisper has much better noise robustness — the escalation path is built in. |
| Safari iOS silent permission quirks (mic permission resets per session on some iOS versions) | Catch permission errors + render "Tap the mic button again" hint. Document in plan if it becomes a support issue. |
| No Firefox desktop support | Feature-detect + hide button. Phase 2 (Whisper) eliminates this gap. Negligible given field-tech mobile skew. |
| Transcripts in DB could contain customer PII (names, property details) | Only the final transcript is written to the field the user is dictating into — same privacy posture as typing into the same field. The `voice.dictated` event carries NO transcript content. |
| Mic button adds UI clutter | Only render when supported. Keep the icon small (same size as existing inline action icons per CLAUDE.md UI standards). Hide entirely if no browser support. |

## 5. Out of scope

- Voice *output* (TTS) — Phase 3 concern. Phase 1 is input-only.
- Wake-word "Hey DeepBlue" — Phase 3.
- Voice commands that navigate/act (beyond inserting dictated text) — Phase 3.
- Multi-language — Phase 1 ships `en-US` only. Adding `es-MX` is one line when demand exists.
- Offline transcription — all three phases require an internet connection.

## 6. References

- [MDN — Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) — the browser-native path Phase 1 uses.
- [Groq Whisper pricing + docs](https://console.groq.com/docs/speech-text) — Phase 2 backend.
- [Deepgram Nova-2 streaming docs](https://developers.deepgram.com/) — Phase 3 streaming STT.
- [ElevenLabs TTS docs](https://elevenlabs.io/docs) — Phase 3 TTS.
- FB-29 feedback record (parked as `planned` 2026-04-20).
- Current code: `frontend/src/components/deepblue/chat-input.tsx`, `inbox/thread-detail-sheet.tsx`, `jobs/action-detail-content.tsx` — Phase 1 mount sites.
