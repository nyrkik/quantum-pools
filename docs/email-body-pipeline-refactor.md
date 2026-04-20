# Email body pipeline refactor — adopt the canonical 3-stage model

> **Status:** shipped 2026-04-20 across commits `20215e8` (plan) →
> `7e059d3` (pipeline) → `8b7064b` (from_name). Backfill committed,
> post-ship audit returns zero rows with QP tokens / mojibake /
> zero-widths across both message bodies and thread snippets. Kept
> as implementation reference for ~1–2 weeks; remove after dogfood
> stabilization confirms no regressions. Current-state reference is
> `docs/email-pipeline.md`.

## 1. Why

Over the last week three separate customer-reported issues all turned out to be the same class of bug — we were patching symptoms instead of fixing the layer:

1. **Yardi ACH emails** arrived with raw `=3D` / `=09` / `=\n` quoted-printable escapes showing in the inbox row.
2. **AmEx VERP addresses** (`r_07b156d0-…@welcome.americanexpress.com`) displayed instead of the sender's real name.
3. **Stripe / Postmark / Poolcorp emails** showed mojibake — `you'll` as `youâ\x80\x99ll`, `$4,598.19` as `â\x80¢â\x80¢â\x80¢â\x80¢`.

Each one got its own fix (`_normalize_body` with QP decode + HTML strip + MIME unwrap, a backfill script, etc.), but Brian called it correctly: **we're only fixing issues we observe, not the class of bug.** Running a systematic audit of 500 Sapphire messages surfaced seven more stale rows that my bespoke regexes missed.

The root cause is that our body-extraction code has **two stages** of an industry-standard **three-stage pipeline**. Every sophisticated email client (Thunderbird, K-9 Mail, any JMAP server per RFC 8621) uses the same three stages:

```
parse   →   NORMALIZE   →   use
```

We have parse (stdlib `email` with policy support — correct) and use (HTML stripping, reply-chain cleanup). The missing middle stage is where the industry solves:

- **charset-detection fallback** when the declared charset is wrong or missing — `charset-normalizer`
- **mojibake repair** when bytes were correctly decoded per the declaration but the declaration lied — `ftfy`
- **Unicode canonicalization** (NFC) so composed/decomposed forms compare equal
- **zero-width + control-char stripping** so marketer-added spacing characters don't leak into previews

Without the normalize stage, every new sender quirk becomes a bespoke regex in our code. With the normalize stage, **one `fix_text()` + `charset-normalizer` + `NFC` call kills the class of bug**, and anything it can't fix falls back to the JMAP-prescribed behavior (insert `U+FFFD`, keep going — never hard-fail).

Full research (libraries evaluated with GitHub activity checks, benchmarks, RFCs) lives in the refactor conversation thread; the short version is distilled below.

## 2. What changes

### 2.1 New pipeline

```
raw RFC 822 bytes
  │
  ▼  PARSE        email.message_from_bytes(raw, policy=email.policy.default)
  │
  ▼  NORMALIZE    for each text part:
  │                 1. bytes → unicode
  │                      a. try declared Content-Type charset
  │                      b. on UnicodeDecodeError → charset_normalizer.from_bytes(...).best()
  │                      c. fallback: latin-1 with errors='replace'
  │                 2. ftfy.fix_text()  — mojibake + smart-quote recovery
  │                 3. unicodedata.normalize("NFC", …)
  │                 4. strip C0 controls + zero-width (U+200B, U+200C, U+200D, U+FEFF)
  │
  ▼  USE          text/html parts → inscriptis for plaintext,
                  bleach/nh3 for render-safe HTML
                  reply-chain + signature → mail-parser-reply
```

### 2.2 Code shape

**Single public helper** `decode_part(part: email.message.EmailMessage) -> str` in `src/services/agents/mail_agent.py`. Encapsulates the whole normalize stage. Called once per text part inside `extract_bodies` (both paths — multipart walk + single-part fallback).

```python
# signature (no implementation here — lives in the refactor PR)
def decode_part(part: EmailMessage) -> str:
    """Decode a text part's bytes to clean unicode via the canonical
    3-stage normalize: charset fallback → ftfy → NFC + zero-width strip.
    Matches JMAP's best-effort-with-U+FFFD contract — never raises."""
```

The following helpers become smaller or get deleted:

| Helper | Fate |
|---|---|
| `_clean_html` | Keep, narrow to "strip HTML tags for plain-text preview". Delegate to `inscriptis.get_text()` for the heavy lifting. |
| `_normalize_body` | **Delete** after refactor — its job is subsumed by `decode_part`. QP re-decode + HTML-in-plaintext detect + flag dict → all replaced by the pipeline + richer event flags emitted from `decode_part`. |
| `_unwrap_embedded_mime` | Keep — handles the Outlook/Exchange multipart-in-TextBody envelope quirk, which is a structural issue not a decode issue. Still runs pre-`decode_part`. |
| `strip_quoted_reply` / `strip_email_signature` | **Replace** with `mail-parser-reply`. Multi-language (en/de/fr/it/ja/pl) out of the box; our regex path is English-only and brittle. |
| `_looks_quoted_printable` / `_decode_quoted_printable` / `_looks_like_html` / `_QP_TOKEN_RE` / `_HTML_TAG_RE` | **Delete** — stdlib `email` handles CTE decoding when we pass `get_payload(decode=True)`. The QP-escapes-in-text-part quirk was a symptom of not normalizing per-part; `decode_part` handles it by definition. |

### 2.3 From header — `from_name` as a first-class column

Separate concern from body pipeline, but in the same refactor because they were reported together:

- Migration: add `agent_messages.from_name VARCHAR(200) NULL`. Nullable; population only on new ingests + best-effort backfill from raw bytes where available.
- Ingest: use `email.headerregistry.Address` (Python 3.6+, RFC 5322-compliant) instead of the `parseaddr` regex. Populates both `from_email` and `from_name`.
- Presenter: when `matched_customer_id IS NULL` and `contact_person_name IS NULL` and `from_name IS NOT NULL`, surface `from_name` as the display. For legacy rows with `from_name IS NULL`, fall back to a VERP-aware prettifier: if the local part looks opaque (`r_`-prefix + hex blob, `b-` prefix, `=` in local-part), display the domain alone; otherwise display the email.

### 2.4 Observability — extend `email.body_normalized`

Current flags: `mime_unwrapped`, `qp_decoded`, `html_stripped_from_text`.

Add to payload (only when the transform fired — key-present = flag-true):

| Flag | Fires when |
|---|---|
| `charset_fallback_used` | declared charset failed; `charset-normalizer` picked something else |
| `mojibake_repaired` | `ftfy.fix_text` changed the text non-trivially (not just whitespace) |
| `zero_width_stripped` | at least one U+200B/C/D or U+FEFF removed |
| `reply_chain_stripped` | `mail-parser-reply` trimmed quoted content |

Consumers stay forward-compatible — filter by key presence. Taxonomy entry gets the new flag list in the same commit as the first emit site (R1 enforcer rule).

### 2.5 Dependencies

```toml
ftfy                 = "^6.3"   # mojibake repair
charset-normalizer   = "^3.4"   # charset detection fallback
inscriptis           = "^2.7"   # HTML → plaintext
mail-parser-reply    = "*"      # reply-chain + signature strip
```

`bleach` / `nh3` for rendering-side HTML sanitization is **out of scope** for this refactor. That's an outbound-iframe concern worth a separate plan.

## 3. How — rollout sequence

1. **Commit the plan** (this doc) + update the Documentation Index in CLAUDE.md.
2. **Install deps** in `app/pyproject.toml` (or wherever deps live) + `uv sync` / `pip install`.
3. **Build `decode_part`** + unit tests covering: wrong declared charset produces clean unicode, pre-mojibaked text fixes up, zero-widths stripped, NFC applied.
4. **Refactor `extract_bodies`** to call `decode_part` instead of the current ad-hoc decode + `_normalize_body` chain. Return diagnostics dict with richer flags.
5. **Delete superseded helpers** (`_normalize_body`, `_looks_quoted_printable`, `_decode_quoted_printable`, `_QP_TOKEN_RE`, `_HTML_TAG_RE`) + `_clean_html` reduction to an `inscriptis` wrapper. Prune their tests.
6. **Migrate `from_name`** (Alembic: add column, nullable). Update both ingest paths to populate it via `Address`. Update `ThreadPresenter` contact-name logic to consider `from_name` after customer match + CustomerContact fallback.
7. **Replace `strip_quoted_reply` / `strip_email_signature`** with `mail-parser-reply` wherever they're called.
8. **Backfill pass**:
   - Re-run body normalization on all `agent_messages` rows whose body still contains QP tokens / zero-widths / suspected mojibake (`ftfy.fix_and_explain` ≠ unchanged).
   - Refresh `agent_threads.last_snippet` for every thread whose snippet differs after re-deriving from the cleaned body.
   - For rows with `from_name IS NULL`: we can't recover the original From header (discarded at ingest), so this field stays null for historical rows. Log the count to set expectations.
9. **Extend `email.body_normalized`** event with new flag keys. Update taxonomy in the same commit. R1 enforcer verifies.
10. **Deploy**, then run the audit script from the original investigation — expect zero QP tokens, zero mojibake, zero stale snippets. Any remaining rows are a new quirk class worth logging.

Each step is its own commit — the plan shouldn't be one giant PR.

## 4. Definition of done

1. `decode_part` is the single path for per-part text decoding. No other function in `src/` reaches into `part.get_payload` + `.decode(charset, …)` directly.
2. `_normalize_body` and the QP / HTML-specific helpers are deleted; their tests are removed or subsumed.
3. `ftfy`, `charset-normalizer`, `inscriptis`, `mail-parser-reply` are listed in project deps with pinned major versions.
4. `agent_messages.from_name` column exists; new ingests populate it; the presenter uses it before falling back to email-local prettification.
5. Backfill has run against Sapphire — the audit query (`body ~ '=[0-9A-Fa-f]{2}' OR body ~ U&'\FFFD' OR last_snippet ~ '=[\r]?\n'`) returns zero rows immediately after.
6. Taxonomy lists the new `email.body_normalized` flag keys; R1 enforcer green.
7. Deploy succeeded; `scripts/audit_event_discipline.py` passes; existing mail tests still pass plus new `decode_part` tests.
8. This doc is updated with a "Status: shipped YYYY-MM-DD" note and a one-line pointer to `docs/email-pipeline.md` for the current-state description.

## 5. Risks and trade-offs

| Risk | Mitigation |
|---|---|
| `ftfy.fix_text()` default uncurls quotes — could rewrite legit curled quotes in HTML emails | Use `fix_text(…, uncurl_quotes=False)` or a custom `TextFixerConfig`. Decide during implementation based on visual spot-check. |
| `mail-parser-reply` has 78 GitHub stars + one maintainer | Pin version; vendor into `app/third_party/` if it ever goes dormant. Sapphire English-only today so worst case is falling back to the existing regex for a release. |
| `charset-normalizer` is pure-Python and slow on large bodies | Cap invocation at bodies ≤ 100 KB (email-realistic). Attachments are parsed separately. |
| New deps widen the attack surface | All four are audited pure-Python libs with no native code except via stdlib. `bleach/nh3` (the one Rust-backed lib) is explicitly out of scope for this refactor. |
| Historical `from_name IS NULL` rows stay null forever — no nice display for legacy VERP senders | Backfill script logs the count. Frontend fallback uses the domain (`welcome.americanexpress.com`). Acceptable degrade. |
| Removing `strip_quoted_reply` breaks something the AI drafting pipeline was relying on | `mail-parser-reply` is a superset — English behavior should match. Run the reply-ingest tests after swap; keep the old helper available for one release as a fallback import. |
| ftfy could touch content that isn't actually mojibake | `fix_and_explain()` logging for the first 7 days of deploy. Review explanations; tighten config if we see false positives. |

## 6. Out of scope for this refactor

- **Outbound HTML sanitization** (`bleach` / `nh3` on the compose path). Separate plan worth writing.
- **Attachment handling changes**. Same pipeline applies in principle but separate review.
- **DSN / bounce detection** as first-class ingest state. Today we store DSNs as regular messages; cleaning that up is a separate ingest feature.
- **Deeper VERP / bounce classification** ("this is actually a Stripe webhook notification, route to X"). Rule-engine concern, separate surface.

## 7. References

- [RFC 8621 — JMAP for Mail §4.2](https://datatracker.ietf.org/doc/html/rfc8621#section-4.2) — `bodyValues` decode + `U+FFFD` on malformed rule
- [Python `email.headerregistry` docs](https://docs.python.org/3/library/email.headerregistry.html) — RFC 5322 compliant `Address`
- [rspeer/python-ftfy](https://github.com/rspeer/python-ftfy) — mojibake repair, <1 FP per 30M tweets
- [jawah/charset_normalizer](https://github.com/jawah/charset_normalizer) — chardet replacement, active
- [weblyzard/inscriptis (JOSS paper)](https://www.theoj.org/joss-papers/joss.03557/10.21105.joss.03557.pdf) — highest recall + F1 for HTML→text
- [alfonsrv/mail-parser-reply](https://github.com/alfonsrv/mail-parser-reply) — reply-chain stripper (successor to abandoned talon)
- Current code: `app/src/services/agents/mail_agent.py`, `app/src/services/inbound_email_service.py`, `app/src/services/gmail/sync.py`
