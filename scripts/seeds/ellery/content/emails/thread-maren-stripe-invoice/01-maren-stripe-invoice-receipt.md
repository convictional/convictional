---
key: msg-maren-stripe-invoice-receipt
model: EmailMessage
thread: !ref thread-maren-stripe-invoice
user: !ref maren
message_type: received
sender: "Stripe <invoicing@stripe.com>"
to:
  - !ref maren
subject: "Your receipt from Ellery"
received_at: !relative_day {offset: -5, hour: 8, tz: America/New_York}
labels: [inbox]
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;">
<tr><td style="background-color:#635bff;padding:20px 24px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:20px;font-weight:bold;">Stripe</span>
</td></tr>
<tr><td style="padding:24px;font-family:Arial,sans-serif;font-size:14px;color:#333333;">
<p style="font-size:16px;font-weight:bold;color:#1a1a1a;">Receipt from Ellery — Legaltech Conference</p>
<p>A payment of <strong>$1,195.00</strong> was made on April 16, 2026.</p>

<table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse;margin:16px 0;border:1px solid #e5e7eb;">
<tr style="background-color:#f9fafb;">
<th align="left" style="font-size:12px;color:#666;padding:8px;border-bottom:1px solid #e5e7eb;">Description</th>
<th align="right" style="font-size:12px;color:#666;padding:8px;border-bottom:1px solid #e5e7eb;">Amount</th>
</tr>
<tr>
<td style="padding:8px;border-bottom:1px solid #f0f0f0;">LegalOps Summit 2026 — Full Conference Pass (1 attendee)</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;">$995.00</td>
</tr>
<tr>
<td style="padding:8px;border-bottom:1px solid #f0f0f0;">Workshop: AI Contracting Tools in Practice</td>
<td align="right" style="padding:8px;border-bottom:1px solid #f0f0f0;">$200.00</td>
</tr>
<tr style="background-color:#f9fafb;">
<td style="padding:8px;font-weight:bold;">Total charged</td>
<td align="right" style="padding:8px;font-weight:bold;">$1,195.00</td>
</tr>
</table>

<p style="color:#666;font-size:12px;">Card charged: Visa ending in 4422 &bull; Transaction ID: pi_3Qw2Xk2eZvKYlo2C1DmPq8vT</p>
<p style="text-align:center;margin-top:20px;">
<span style="background-color:#635bff;color:#ffffff;padding:10px 24px;font-size:13px;">View receipt</span>
</p>
</td></tr>
<tr><td style="background-color:#f9fafb;padding:12px 24px;text-align:center;font-family:Arial,sans-serif;font-size:11px;color:#888888;">
Stripe Inc. &bull; 510 Townsend St, San Francisco, CA 94103 &bull; <a href="#" style="color:#888888;">View in dashboard</a>
</td></tr>
</table>
