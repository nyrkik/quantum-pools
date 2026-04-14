/**
 * Cloudflare Email Worker — receives inbound email for sapphire-pools.com
 * and POSTs it to the QuantumPools webhook endpoint.
 *
 * Extracts: from, to, subject, body, headers, date, message-id
 * Converts to the same format our webhook handler expects.
 */

export interface Env {
  WEBHOOK_URL: string;
  // Shared secret matching POSTMARK_WEBHOOK_TOKEN on the QP backend. Set via
  // `wrangler secret put WEBHOOK_TOKEN` — never committed to wrangler.toml.
  WEBHOOK_TOKEN: string;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const { from, to, headers } = message;

    // Read the raw email body
    const rawEmail = await new Response(message.raw).text();

    // Extract plain text body from raw email
    const bodyText = extractTextBody(rawEmail);

    // Build headers dict
    const hdrs: Record<string, string> = {};
    headers.forEach((value, key) => {
      hdrs[key] = value;
    });

    // Build payload matching our generic webhook format
    const payload = {
      from_email: from,
      to_email: to,
      subject: headers.get("subject") || "",
      body_plain: bodyText,
      body_html: extractHtmlBody(rawEmail),
      headers: {
        "Message-ID": headers.get("message-id") || "",
        "Date": headers.get("date") || "",
        "In-Reply-To": headers.get("in-reply-to") || "",
        "References": headers.get("references") || "",
        "Delivered-To": to,
      },
    };

    // POST to our webhook with the shared-secret auth header. Backend gates
    // this endpoint behind X-Webhook-Token (POSTMARK_WEBHOOK_TOKEN env var) —
    // without the header every webhook 401s and we silently lose inbound mail.
    const response = await fetch(env.WEBHOOK_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Webhook-Token": env.WEBHOOK_TOKEN,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      // Log but don't throw — Cloudflare will retry on throw
      console.error(`Webhook failed: ${response.status} ${await response.text()}`);
    }
  },
};

function extractTextBody(raw: string): string {
  // Check if multipart
  const boundaryMatch = raw.match(/boundary="?([^"\r\n;]+)"?/i);
  if (boundaryMatch) {
    const boundary = boundaryMatch[1];
    const parts = raw.split(`--${boundary}`);
    for (const part of parts) {
      if (part.includes("Content-Type: text/plain")) {
        // Find the body after the blank line
        const bodyStart = part.indexOf("\r\n\r\n");
        if (bodyStart >= 0) {
          let body = part.substring(bodyStart + 4).trim();
          // Remove trailing boundary marker
          if (body.endsWith("--")) body = body.slice(0, -2).trim();
          // Handle quoted-printable
          if (part.includes("quoted-printable")) {
            body = decodeQuotedPrintable(body);
          }
          // Handle base64
          if (part.includes("Content-Transfer-Encoding: base64")) {
            try { body = atob(body.replace(/\s/g, "")); } catch {}
          }
          return body;
        }
      }
    }
  }

  // Non-multipart: body is after the first blank line
  const bodyStart = raw.indexOf("\r\n\r\n");
  if (bodyStart >= 0) {
    return raw.substring(bodyStart + 4).trim();
  }
  return raw;
}

function extractHtmlBody(raw: string): string {
  const boundaryMatch = raw.match(/boundary="?([^"\r\n;]+)"?/i);
  if (!boundaryMatch) return "";

  const boundary = boundaryMatch[1];
  const parts = raw.split(`--${boundary}`);
  for (const part of parts) {
    if (part.includes("Content-Type: text/html")) {
      const bodyStart = part.indexOf("\r\n\r\n");
      if (bodyStart >= 0) {
        let body = part.substring(bodyStart + 4).trim();
        if (body.endsWith("--")) body = body.slice(0, -2).trim();
        if (part.includes("quoted-printable")) {
          body = decodeQuotedPrintable(body);
        }
        if (part.includes("Content-Transfer-Encoding: base64")) {
          try { body = atob(body.replace(/\s/g, "")); } catch {}
        }
        return body;
      }
    }
  }
  return "";
}

function decodeQuotedPrintable(str: string): string {
  return str
    .replace(/=\r?\n/g, "")  // soft line breaks
    .replace(/=([0-9A-Fa-f]{2})/g, (_, hex) =>
      String.fromCharCode(parseInt(hex, 16))
    );
}
