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
