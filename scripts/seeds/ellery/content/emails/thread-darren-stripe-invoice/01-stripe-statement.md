---
key: msg-stripe-statement
model: EmailMessage
thread: !ref thread-darren-stripe-invoice
user: !ref darren
message_type: received
sender: "Stripe <invoicing@stripe.com>"
to:
  - !ref darren
subject: "Your March statement is ready"
received_at: !relative_day {offset: -5, hour: 6, tz: America/New_York}
labels: [inbox]
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">
<tr><td style="background-color:#635bff;padding:18px 20px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:18px;font-weight:bold;">Stripe</span>
</td></tr>
<tr><td style="padding:24px 20px;font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;">
<p>Your March statement for <strong>Ellery, Inc.</strong> is ready.</p>

<table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse;margin:16px 0;">
<tr style="background-color:#f6f9fc;">
<th align="left" style="font-family:Arial,sans-serif;font-size:12px;border-bottom:2px solid #635bff;">Line item</th>
<th align="right" style="font-family:Arial,sans-serif;font-size:12px;border-bottom:2px solid #635bff;">Amount</th>
</tr>
<tr>
<td style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border-bottom:1px solid #f0f0f0;">Subscription revenue collected</td>
<td align="right" style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border-bottom:1px solid #f0f0f0;">$148,420.00</td>
</tr>
<tr>
<td style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border-bottom:1px solid #f0f0f0;">Annual prepayments</td>
<td align="right" style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border-bottom:1px solid #f0f0f0;">$32,000.00</td>
</tr>
<tr>
<td style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border-bottom:1px solid #f0f0f0;">Stripe fees</td>
<td align="right" style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border-bottom:1px solid #f0f0f0;">-$5,238.29</td>
</tr>
<tr style="background-color:#f6f9fc;">
<td style="font-family:Arial,sans-serif;font-size:14px;font-weight:bold;padding:8px;"><strong>Net deposited</strong></td>
<td align="right" style="font-family:Arial,sans-serif;font-size:14px;font-weight:bold;padding:8px;"><strong>$175,181.71</strong></td>
</tr>
</table>

<p>Full statement available in the Stripe Dashboard.</p>

<p style="text-align:center;padding:10px 0;">
<span style="background-color:#635bff;color:#ffffff;padding:10px 24px;font-family:Arial,sans-serif;font-size:13px;">View Statement</span>
</p>
</td></tr>
<tr><td style="background-color:#f6f9fc;padding:12px 20px;text-align:center;font-family:Arial,sans-serif;font-size:11px;color:#888888;">
Stripe &bull; 354 Oyster Point Blvd, South San Francisco, CA &bull; <a href="#" style="color:#888888;">Email preferences</a>
</td></tr>
</table>
