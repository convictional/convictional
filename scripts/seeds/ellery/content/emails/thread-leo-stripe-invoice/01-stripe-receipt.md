---
key: msg-leo-stripe-receipt
model: EmailMessage
thread: !ref thread-leo-stripe-invoice
user: !ref leo
message_type: received
sender: "Stripe <receipts@stripe.com>"
to:
  - !ref leo
subject: "Your receipt"
received_at: !relative_day {offset: -4, hour: 8, tz: America/New_York}
labels: [inbox]
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,sans-serif;">
<tr>
  <td style="background-color:#635bff;padding:20px 24px;">
    <span style="color:#ffffff;font-size:18px;font-weight:bold;">Stripe</span>
  </td>
</tr>
<tr>
  <td style="padding:24px;background-color:#ffffff;">
    <p style="font-size:20px;color:#1a1a1a;font-weight:bold;margin:0 0 8px 0;">$79.00</p>
    <p style="font-size:13px;color:#555;margin:0 0 20px 0;">Paid on April 17, 2026 &bull; Receipt #9823-4401</p>
    <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse;font-size:13px;color:#1a1a1a;border:1px solid #e0e0e0;">
      <tr style="background-color:#f9f9f9;">
        <td style="border-bottom:1px solid #e0e0e0;padding:10px;"><strong>Description</strong></td>
        <td style="border-bottom:1px solid #e0e0e0;padding:10px;text-align:right;"><strong>Amount</strong></td>
      </tr>
      <tr>
        <td style="border-bottom:1px solid #e0e0e0;padding:10px;">Product management tools subscription (monthly)</td>
        <td style="border-bottom:1px solid #e0e0e0;padding:10px;text-align:right;">$79.00</td>
      </tr>
      <tr style="background-color:#f9f9f9;">
        <td style="padding:10px;"><strong>Total</strong></td>
        <td style="padding:10px;text-align:right;"><strong>$79.00</strong></td>
      </tr>
    </table>
  </td>
</tr>
<tr>
  <td style="background-color:#f6f6f6;padding:12px 24px;text-align:center;font-size:11px;color:#888;">
    Stripe, Inc. &bull; 354 Oyster Point Blvd, South San Francisco, CA
  </td>
</tr>
</table>
