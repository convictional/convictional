---
key: msg-mateo-stripe-receipt
model: EmailMessage
thread: !ref thread-mateo-stripe
user: !ref mateo
message_type: received
sender: "Stripe <receipts@stripe.com>"
to:
  - !ref mateo
subject: "Your receipt from Ellery AI, Inc."
received_at: !relative_day {offset: -4, hour: 6, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,Helvetica,sans-serif;">
<tr>
  <td style="background-color:#635bff;padding:16px 20px;">
    <span style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">stripe</span>
  </td>
</tr>
<tr>
  <td style="padding:20px;background-color:#ffffff;color:#32325d;font-size:14px;">
    <p style="margin-top:0;font-size:16px;font-weight:bold;color:#32325d;">Receipt from Ellery AI, Inc.</p>
    <p style="color:#6b7c93;font-size:13px;margin-top:-8px;">April 17, 2026</p>

    <table width="100%" cellpadding="8" cellspacing="0" style="border:1px solid #e6ebf1;border-radius:4px;margin:16px 0;">
      <tr style="border-bottom:1px solid #e6ebf1;">
        <td style="font-size:13px;color:#6b7c93;">Business development — prospect travel (NYC)</td>
        <td style="text-align:right;font-size:13px;color:#32325d;white-space:nowrap;"><strong>$148.00</strong></td>
      </tr>
      <tr>
        <td style="font-size:13px;color:#6b7c93;">Sales enablement tools — monthly</td>
        <td style="text-align:right;font-size:13px;color:#32325d;white-space:nowrap;"><strong>$79.00</strong></td>
      </tr>
      <tr style="background-color:#f8fafc;">
        <td style="font-size:13px;font-weight:bold;color:#32325d;">Total</td>
        <td style="text-align:right;font-size:14px;font-weight:bold;color:#32325d;"><strong>$227.00</strong></td>
      </tr>
    </table>

    <p style="font-size:13px;color:#6b7c93;">Payment method: Visa ending in 4782</p>

    <p style="font-size:12px;color:#8898aa;margin-top:24px;">This receipt was sent to mateo@ellery.ai. <a href="#" style="color:#635bff;">Download PDF</a> · <a href="#" style="color:#8898aa;">Manage billing</a></p>
  </td>
</tr>
</table>
