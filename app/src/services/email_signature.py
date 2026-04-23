"""Signature composition — single source of truth for outbound signature format.

Composes the plain-text + HTML signature shown at the bottom of every
customer-facing email. Honors the admin-level auto-prepend and logo
toggles; falls back cleanly when per-user signature isn't set.

Order of the assembled signature (from top):

    [user body text]

    --
    {sender first name}               ← if auto_signature_prefix
    {org name}                        ← if auto_signature_prefix and
                                         user's signature doesn't already
                                         start with it
    {user's signature text}           ← user-level; falls back to
                                         organization.agent_signature
    [logo]                            ← HTML only; if
                                         include_logo_in_signature + logo_url

HTML variant autolinks emails, phone numbers, and bare domains in the
user's signature text block so recipients can click. Plain text stays
raw — mail clients handle that themselves.

Rendering callers should NOT prepend `\\n\\n--\\n` themselves — use
`compose_signature()` to build the full signature block, then append it
to the body with the separator already baked in.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass


# Regex — conservative on purpose. Linkify recognizable emails / phones /
# bare domains, but never rewrite arbitrary substrings. Wrong false positives
# here show up in every customer email, so err on the strict side.
_EMAIL_RE = re.compile(r"(?<![\w.+-])([\w.+-]+@[\w-]+\.[\w.-]+)(?![\w-])")
_PHONE_RE = re.compile(
    r"(?<![\w])("
    r"\+?1?[-.\s]?"
    r"\(?\d{3}\)?[-.\s]?"
    r"\d{3}[-.\s]?"
    r"\d{4}"
    r")(?![\w])"
)
_URL_RE = re.compile(r"\bhttps?://[^\s<>]+", re.IGNORECASE)
# Bare domain: word.tld[/...], requires at least one dot, no schema.
# Restrict TLD length 2-24 to avoid matching words like "e.g." or "p.s."
_BARE_DOMAIN_RE = re.compile(
    r"(?<![\w.+-@])"
    r"((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}"
    r"(?:/[^\s<>]*)?)"
    r"(?![\w])",
    re.IGNORECASE,
)


@dataclass
class SignatureOutput:
    plain: str  # Plain-text block to append to text body (already includes the "--" separator).
    html: str   # HTML block (<div>...</div>) to append to the HTML body.
    logo_inline: dict | None = None  # None, or {"content_bytes": ..., "filename": ..., "content_id": ..., "mime_type": ...}


def compose_signature(
    *,
    sender_first_name: str | None,
    org_name: str | None,
    auto_signature_prefix: bool,
    user_signature: str | None,
    org_signature: str | None,
    include_logo: bool,
    logo_url: str | None,
    logo_bytes: bytes | None = None,
    logo_mime_type: str | None = None,
    user_signoff: str | None = None,
    website_url: str | None = None,
) -> SignatureOutput:
    """Assemble the full signature block (plain + html) and optional logo.

    Callers are responsible for fetching logo_bytes (with caching) before
    calling — this module doesn't do network I/O.
    """
    # Signature tail: user's personal text (phone, title, etc.) ABOVE the
    # shared org footer (contact info, domain). Both render when both are
    # set — the org footer is the standardized tail every outbound shares.
    # Line-level dedup across the two sources + against auto-prepended
    # prefix lines so org_name / duplicate contact rows never repeat.
    user_text = (user_signature or "").strip()
    org_text = (org_signature or "").strip()

    def _lines_iter(*sources: str):
        for s in sources:
            for raw in s.splitlines():
                yield raw

    tail_lines: list[str] = []
    seen_norm: set[str] = set()
    for raw in _lines_iter(user_text, org_text):
        stripped = raw.strip()
        if not stripped:
            # Preserve structural blanks as long as they aren't leading and
            # don't create consecutive duplicates.
            if tail_lines and tail_lines[-1] != "":
                tail_lines.append("")
            continue
        norm = stripped.lower()
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        tail_lines.append(stripped)
    # Trim trailing blanks.
    while tail_lines and tail_lines[-1] == "":
        tail_lines.pop()

    signoff = (user_signoff or "").strip() or None

    prefix_lines: list[str] = []
    if auto_signature_prefix:
        if sender_first_name:
            name = sender_first_name.strip()
            if name.lower() not in seen_norm:
                prefix_lines.append(name)
                seen_norm.add(name.lower())
        if org_name:
            org_name_clean = org_name.strip()
            if org_name_clean.lower() not in seen_norm:
                prefix_lines.append(org_name_clean)
                seen_norm.add(org_name_clean.lower())
            else:
                # Already in tail (user typed it, or org footer starts
                # with it) — drop it from the tail too so it renders ONCE
                # at the prefix position rather than leaking into the tail.
                org_lower = org_name_clean.lower()
                tail_lines = [ln for ln in tail_lines if ln.strip().lower() != org_lower]
                prefix_lines.append(org_name_clean)

    sig_tail = "\n".join(tail_lines)

    plain_lines: list[str] = []
    plain_lines.extend(prefix_lines)
    if sig_tail:
        plain_lines.append(sig_tail)

    if not plain_lines and not signoff:
        return SignatureOutput(plain="", html="", logo_inline=None)

    # Plain text layout: body is already in caller's text. Sign-off goes
    # on its own line above the name block. No "--" separator (modern
    # business style).
    plain_parts: list[str] = []
    if signoff:
        plain_parts.append(f"\n\n{signoff}")
    if plain_lines:
        # Leading blank line only if there wasn't a sign-off above (the
        # sign-off already inserted one). Single blank line between
        # sign-off and the name block.
        sep = "\n\n" if not signoff else "\n\n"
        plain_parts.append(sep + "\n".join(plain_lines))
    plain_block = "".join(plain_parts)

    # HTML block. Autolink user's signature text only — prefix lines are
    # name/org, no links needed.
    html_lines: list[str] = []
    if signoff:
        html_lines.append(html.escape(signoff))
        html_lines.append("")  # blank line between sign-off and name
    for line in prefix_lines:
        html_lines.append(html.escape(line))
    if sig_tail:
        for raw_line in sig_tail.splitlines():
            stripped = raw_line.strip()
            html_lines.append(_autolink_line(stripped) if stripped else "")

    html_body = "<div style=\"color:#444;font-size:13px;line-height:1.4;margin-top:16px;padding-top:12px;border-top:1px solid #e5e7eb;\">"
    html_body += "<br>".join(html_lines)

    logo_inline: dict | None = None
    if include_logo and logo_url and logo_bytes:
        content_id = "qp-signature-logo"
        mime = logo_mime_type or _guess_mime_from_url(logo_url)
        logo_inline = {
            "content_bytes": logo_bytes,
            "filename": _filename_from_url(logo_url) or "logo.png",
            "content_id": content_id,
            "mime_type": mime,
        }
        # Append logo as last line of the HTML signature. `cid:` reference
        # uses the same content_id the attachment declares. When a website
        # URL is configured, wrap the <img> in an <a> so recipients can
        # click through to the org's public site.
        img_tag = (
            f"<img src=\"cid:{content_id}\" alt=\"{html.escape(org_name or '')}\""
            " style=\"max-width:180px;max-height:60px;height:auto;display:inline-block;border:0;\">"
        )
        normalized_site = _normalize_website(website_url)
        logo_html = (
            f'<a href="{html.escape(normalized_site, quote=True)}" style="text-decoration:none;">{img_tag}</a>'
            if normalized_site else img_tag
        )
        html_body += "<br><br>" + logo_html

    html_body += "</div>"

    return SignatureOutput(plain=plain_block, html=html_body, logo_inline=logo_inline)


_LINK_STYLE = 'style="color:#2563eb;text-decoration:underline;"'


def _autolink_line(line: str) -> str:
    """Autolink emails → mailto:, phones → tel:, bare domains → https://.
    Input is already text (no HTML). Output is HTML-safe markup with inline
    styling on anchors so email clients render the familiar blue link
    appearance without depending on stylesheets that get stripped."""
    # Tokenize: walk through the string, finding matches. To keep it simple
    # and avoid double-processing, we find the earliest match of any type
    # and consume it. Non-matching text is HTML-escaped.
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        rest = line[i:]

        # Pick the earliest match across URL / email / phone / bare domain.
        candidates: list[tuple[int, int, str, str]] = []
        m = _URL_RE.search(rest)
        if m:
            candidates.append((m.start(), m.end(), m.group(0), f'<a href="{html.escape(m.group(0), quote=True)}" {_LINK_STYLE}>{html.escape(m.group(0))}</a>'))
        m = _EMAIL_RE.search(rest)
        if m:
            addr = m.group(1)
            candidates.append((m.start(), m.end(), m.group(1), f'<a href="mailto:{html.escape(addr, quote=True)}" {_LINK_STYLE}>{html.escape(addr)}</a>'))
        m = _PHONE_RE.search(rest)
        if m:
            digits = re.sub(r"[^\d+]", "", m.group(1))
            # Normalize to +1NNNNNNNNNN for North America if 10-digit
            tel = digits if digits.startswith("+") else f"+1{digits.lstrip('1')}"
            candidates.append((m.start(), m.end(), m.group(1), f'<a href="tel:{html.escape(tel, quote=True)}" {_LINK_STYLE}>{html.escape(m.group(1))}</a>'))
        m = _BARE_DOMAIN_RE.search(rest)
        if m:
            dom = m.group(1)
            candidates.append((m.start(), m.end(), dom, f'<a href="https://{html.escape(dom, quote=True)}" {_LINK_STYLE}>{html.escape(dom)}</a>'))

        if not candidates:
            out.append(html.escape(rest))
            break

        # Earliest match wins; if multiple start at the same spot, prefer
        # the longest (URL > email > phone > bare domain, naturally the
        # longer match covers better).
        candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))
        start, end, _orig, anchor = candidates[0]
        if start > 0:
            out.append(html.escape(rest[:start]))
        out.append(anchor)
        i += end
    return "".join(out)


def _normalize_website(url: str | None) -> str | None:
    """Return a fully-qualified https:// URL, or None if unusable.
    Accepts bare domains like `sapphire-pools.com` and inflates them."""
    if not url:
        return None
    clean = url.strip()
    if not clean:
        return None
    if clean.lower().startswith(("http://", "https://")):
        return clean
    # Bare domain or relative path — assume https.
    return f"https://{clean}"


def _guess_mime_from_url(url: str) -> str:
    """Derive a mime type from the URL's extension. Conservative default."""
    lower = url.lower().split("?", 1)[0]
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".svg"):
        return "image/svg+xml"
    if lower.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


def _filename_from_url(url: str) -> str | None:
    path = url.split("?", 1)[0].rstrip("/")
    if "/" in path:
        return path.rsplit("/", 1)[1] or None
    return None
