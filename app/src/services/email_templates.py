"""Email templates — plain functions returning (text, html) tuples.

All templates are white-labeled using org_name and branding_color.
"""


def _base_html(org_name: str, branding_color: str, content_html: str) -> str:
    """Wrap content in a consistent email shell."""
    return f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; padding: 32px 0;">
<div style="border-bottom: 3px solid {branding_color}; padding-bottom: 16px; margin-bottom: 24px;">
  <strong style="color: {branding_color}; font-size: 1.125rem;">{org_name}</strong>
</div>
{content_html}
<div style="margin-top: 32px; padding-top: 16px; border-top: 1px solid #e2e8f0; color: #a0aec0; font-size: 0.75rem;">
  Sent by {org_name} via QuantumPools
</div>
</div>"""


def team_invite_template(
    org_name: str,
    user_name: str,
    setup_url: str,
    branding_color: str = "#1a1a2e",
) -> tuple[str, str]:
    """Team member invitation email."""
    text = f"""Hi {user_name},

You've been invited to join {org_name} on QuantumPools.

Click the link below to set up your password and access your account:

{setup_url}

This link will expire in 7 days. If you have questions, reply to this email.

— {org_name}"""

    content = f"""<p style="color: #4a5568; line-height: 1.6;">Hi {user_name},</p>
<p style="color: #4a5568; line-height: 1.6;">You've been invited to join <strong>{org_name}</strong> on QuantumPools.</p>
<p style="margin: 24px 0;">
  <a href="{setup_url}" style="background: {branding_color}; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">Set Up Your Account</a>
</p>
<p style="color: #718096; font-size: 0.875rem;">This link expires in 7 days. If the button doesn't work, copy this URL:<br>
<span style="color: #4a5568; word-break: break-all;">{setup_url}</span></p>"""

    html = _base_html(org_name, branding_color, content)
    return text, html


def invoice_email_template(
    org_name: str,
    customer_name: str,
    invoice_number: str,
    subject: str,
    total: str,
    due_date: str,
    view_url: str,
    branding_color: str = "#1a1a2e",
) -> tuple[str, str]:
    """Invoice email template."""
    text = f"""Hi {customer_name},

{subject}

Invoice #{invoice_number}
Amount due: {total}
Due date: {due_date}

View your invoice: {view_url}

Thank you for your business.

— {org_name}"""

    content = f"""<p style="color: #4a5568; line-height: 1.6;">Hi {customer_name},</p>
<p style="color: #4a5568; line-height: 1.6;">{subject}</p>
<div style="background: #f7fafc; border-radius: 8px; padding: 20px; margin: 20px 0;">
  <table style="width: 100%; border-collapse: collapse;">
    <tr><td style="color: #718096; padding: 4px 0;">Invoice</td><td style="text-align: right; font-weight: 600;">#{invoice_number}</td></tr>
    <tr><td style="color: #718096; padding: 4px 0;">Amount Due</td><td style="text-align: right; font-weight: 600; font-size: 1.125rem; color: {branding_color};">{total}</td></tr>
    <tr><td style="color: #718096; padding: 4px 0;">Due Date</td><td style="text-align: right; font-weight: 600;">{due_date}</td></tr>
  </table>
</div>
<p style="margin: 24px 0;">
  <a href="{view_url}" style="background: {branding_color}; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">View Invoice</a>
</p>
<p style="color: #718096; font-size: 0.875rem;">Thank you for your business.</p>"""

    html = _base_html(org_name, branding_color, content)
    return text, html


def estimate_email_template(
    org_name: str,
    estimate_number: str,
    estimate_subject: str,
    total: str,
    view_url: str,
    property_line: str = "",
    recipient_first_name: str = "",
    branding_color: str = "#1a1a2e",
) -> tuple[str, str]:
    """Estimate email template."""
    greeting = f"Hello {recipient_first_name}," if recipient_first_name else "Hello,"
    location = f" at {property_line}" if property_line else ""
    text = f"""{greeting}

Please find attached an estimate to address {estimate_subject.lower()}{location}.

Estimate #{estimate_number}
Total: {total}

View and approve your estimate: {view_url}

If you have questions, reply to this email.

— {org_name}"""

    location_html = f" at <strong>{property_line}</strong>" if property_line else ""
    content = f"""<p style="color: #4a5568; line-height: 1.6;">{greeting}</p>
<p style="color: #4a5568; line-height: 1.6;">Please find attached an estimate to address {estimate_subject.lower()}{location_html}.</p>
<div style="background: #f7fafc; border-radius: 8px; padding: 20px; margin: 20px 0;">
  <table style="width: 100%; border-collapse: collapse;">
    <tr><td style="color: #718096; padding: 4px 0;">Estimate</td><td style="text-align: right; font-weight: 600;">#{estimate_number}</td></tr>
    <tr><td style="color: #718096; padding: 4px 0;">Total</td><td style="text-align: right; font-weight: 600; font-size: 1.125rem; color: {branding_color};">{total}</td></tr>
  </table>
</div>
<p style="margin: 24px 0;">
  <a href="{view_url}" style="background: {branding_color}; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">View Estimate</a>
</p>
<p style="color: #718096; font-size: 0.875rem;">If you have questions, reply to this email.</p>"""

    html = _base_html(org_name, branding_color, content)
    return text, html


def customer_email_template(
    org_name: str,
    body_text: str,
    branding_color: str = "#1a1a2e",
) -> tuple[str, str]:
    """Customer-facing email (replies, followups, broadcasts).

    Takes the full plain-text body (already includes signature) and wraps it
    in the branded HTML shell. Preserves paragraph breaks as HTML.
    """
    # Plain text is the body as-is
    text = body_text

    # HTML: convert double newlines to paragraph breaks, single to <br>
    import re
    paragraphs = re.split(r"\n{2,}", body_text.strip())
    html_paragraphs = []
    for p in paragraphs:
        # Signature separator
        if p.strip() == "--":
            html_paragraphs.append('<hr style="border: none; border-top: 1px solid #e2e8f0; margin: 16px 0;">')
            continue
        escaped = p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines = escaped.replace("\n", "<br>")
        html_paragraphs.append(f'<p style="color: #4a5568; line-height: 1.6; margin: 0 0 12px 0;">{lines}</p>')

    content = "\n".join(html_paragraphs)
    html = _base_html(org_name, branding_color, content)
    return text, html


def customer_portal_magic_link_template(
    org_name: str,
    contact_name: str,
    login_url: str,
    expires_in_minutes: int = 15,
    branding_color: str = "#1a1a2e",
) -> tuple[str, str]:
    """Sign-in email for the customer portal (passwordless magic link)."""
    text = f"""Hi {contact_name},

Click the link below to sign in to your {org_name} account:

{login_url}

This link expires in {expires_in_minutes} minutes. If you didn't ask to sign in, you can safely ignore this email.

— {org_name}"""

    content = f"""<p style="color: #4a5568; line-height: 1.6;">Hi {contact_name},</p>
<p style="color: #4a5568; line-height: 1.6;">Click below to sign in to your <strong>{org_name}</strong> account:</p>
<p style="margin: 24px 0;">
  <a href="{login_url}" style="background: {branding_color}; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">Sign in</a>
</p>
<p style="color: #718096; font-size: 0.875rem;">This link expires in {expires_in_minutes} minutes. If you didn't ask to sign in, you can safely ignore this email.</p>
<p style="color: #718096; font-size: 0.75rem;">Button not working? Copy this URL:<br>
<span style="color: #4a5568; word-break: break-all;">{login_url}</span></p>"""

    html = _base_html(org_name, branding_color, content)
    return text, html


def dunning_email_template(
    step: int,
    org_name: str,
    customer_name: str,
    invoice_number: str,
    balance: str,
    days_past_due: int,
    pay_url: str,
    branding_color: str = "#1a1a2e",
    late_fee_warning: str | None = None,
) -> tuple[str, str, str]:
    """4-step dunning sequence. Returns (subject, text_body, html_body).

    Step 1 (T+0): neutral — payment couldn't be processed / past due.
    Step 2 (T+3): polite, direct CTA to update payment.
    Step 3 (T+7): escalating — service is at risk.
    Step 4 (T+14): final notice — service review pending.

    Tone escalates each step. Single CTA per email. The pay_url is the
    /pay/{token} public page (handles both card payment and bank ACH).

    `late_fee_warning` is an optional one-line nudge about an impending
    late fee. Surfaced on step 4 (final notice) when the org has late
    fees enabled and the invoice is approaching the grace window. None
    means the line is omitted entirely.
    """
    if step == 1:
        subject = f"Payment issue on invoice #{invoice_number}"
        headline = "Your payment couldn't be processed"
        body = (
            f"Hi {customer_name}, we weren't able to collect payment on invoice "
            f"#{invoice_number} ({balance}). This is usually a card-on-file issue "
            f"— an expired card or a temporary hold. Please update your payment "
            f"method or pay this invoice when you have a moment."
        )
        cta = "Pay invoice"
    elif step == 2:
        subject = f"Action required — invoice #{invoice_number} is {days_past_due} days past due"
        headline = "Action required: update your payment"
        body = (
            f"Hi {customer_name}, invoice #{invoice_number} ({balance}) is now "
            f"{days_past_due} days past due. Please update your payment method or "
            f"pay this invoice today to keep your account in good standing."
        )
        cta = "Pay now"
    elif step == 3:
        subject = f"Your {org_name} service is at risk"
        headline = "Your service is at risk"
        body = (
            f"Hi {customer_name}, invoice #{invoice_number} ({balance}) is now "
            f"{days_past_due} days past due. If we don't receive payment soon, "
            f"your service may be paused. Please pay this invoice today to keep "
            f"your service uninterrupted."
        )
        cta = "Pay now to keep service"
    else:  # step >= 4
        subject = f"Final notice — invoice #{invoice_number}"
        headline = "Final notice — service review pending"
        body = (
            f"Hi {customer_name}, invoice #{invoice_number} ({balance}) is now "
            f"{days_past_due} days past due. This account will be reviewed for "
            f"service hold. To prevent service interruption, please pay this "
            f"invoice immediately or contact {org_name} directly."
        )
        if late_fee_warning:
            body = f"{body}\n\n{late_fee_warning}"
        cta = "Pay now"

    text = f"""Hi {customer_name},

{headline}

{body}

Pay: {pay_url}

— {org_name}"""

    body_html = body.replace("\n\n", "</p>\n<p style=\"color: #4a5568; line-height: 1.6;\">")
    content = f"""<h2 style="color: #1a1a2e; margin-bottom: 8px; font-size: 1.125rem;">{headline}</h2>
<p style="color: #4a5568; line-height: 1.6;">{body_html}</p>
<p style="margin: 24px 0;">
  <a href="{pay_url}" style="background: {branding_color}; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">{cta}</a>
</p>
<p style="color: #718096; font-size: 0.75rem;">Button not working? Copy this URL:<br>
<span style="color: #4a5568; word-break: break-all;">{pay_url}</span></p>"""

    html = _base_html(org_name, branding_color, content)
    return subject, text, html


def password_reset_template(
    org_name: str,
    user_name: str,
    reset_url: str,
    expires_in_hours: int = 1,
    branding_color: str = "#1a1a2e",
) -> tuple[str, str]:
    """Password reset email with token link."""
    text = f"""Hi {user_name},

We received a request to reset the password for your {org_name} account.

Click the link below to choose a new password:

{reset_url}

This link will expire in {expires_in_hours} hour(s). If you didn't request this, you can ignore this email — your password will stay the same.

— {org_name}"""

    content = f"""<p style="color: #4a5568; line-height: 1.6;">Hi {user_name},</p>
<p style="color: #4a5568; line-height: 1.6;">We received a request to reset the password for your <strong>{org_name}</strong> account.</p>
<p style="margin: 24px 0;">
  <a href="{reset_url}" style="background: {branding_color}; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">Reset Password</a>
</p>
<p style="color: #718096; font-size: 0.875rem;">This link expires in {expires_in_hours} hour(s). If you didn't request this, ignore this email — your password will stay the same.</p>
<p style="color: #718096; font-size: 0.75rem;">Button not working? Copy this URL:<br>
<span style="color: #4a5568; word-break: break-all;">{reset_url}</span></p>"""

    html = _base_html(org_name, branding_color, content)
    return text, html


def password_changed_template(
    org_name: str,
    user_name: str,
    branding_color: str = "#1a1a2e",
) -> tuple[str, str]:
    """Notification that password was changed."""
    text = f"""Hi {user_name},

Your password for {org_name} was just changed.

If you made this change, you can ignore this email. If you didn't, contact your organization admin immediately — your account may be compromised.

— {org_name}"""

    content = f"""<p style="color: #4a5568; line-height: 1.6;">Hi {user_name},</p>
<p style="color: #4a5568; line-height: 1.6;">Your password for <strong>{org_name}</strong> was just changed.</p>
<p style="color: #4a5568; line-height: 1.6;">If you made this change, you can ignore this email. If you didn't, contact your organization admin immediately — your account may be compromised.</p>"""

    html = _base_html(org_name, branding_color, content)
    return text, html


def notification_template(
    org_name: str,
    title: str,
    body: str,
    branding_color: str = "#1a1a2e",
) -> tuple[str, str]:
    """Generic notification email."""
    text = f"""{title}

{body}

— {org_name}"""

    # Convert newlines to <br> for HTML body
    html_body = body.replace("\n", "<br>")
    content = f"""<h2 style="color: #1a1a2e; margin-bottom: 8px; font-size: 1.125rem;">{title}</h2>
<p style="color: #4a5568; line-height: 1.6;">{html_body}</p>"""

    html = _base_html(org_name, branding_color, content)
    return text, html
