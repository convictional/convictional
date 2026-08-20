---
key: theo-expense-01-ramp-expense
model: EmailMessage
thread: !ref thread-theo-expense
user: !ref theo
message_type: received
sender: "Ramp <notifications@ramp.com>"
to:
  - !ref theo
subject: "Please categorize this expense"
received_at: !relative_day {offset: -3, hour: 9, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">
<tr><td style="background-color:#131313;padding:16px 20px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">Ramp</span>
</td></tr>
<tr><td style="padding:20px;font-family:Arial,sans-serif;font-size:14px;color:#1d1d1d;">

<p>A new charge appeared on your Ramp card that needs a category and memo.</p>

<table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse;margin:12px 0;">
<tr style="background-color:#f6f8fa;">
<td style="font-family:Arial,sans-serif;font-size:12px;color:#586069;padding:6px 8px;border:1px solid #e1e4e8;">Merchant</td>
<td style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border:1px solid #e1e4e8;font-weight:bold;">GitHub, Inc.</td>
</tr>
<tr>
<td style="font-family:Arial,sans-serif;font-size:12px;color:#586069;padding:6px 8px;border:1px solid #e1e4e8;">Amount</td>
<td style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border:1px solid #e1e4e8;">$4.00</td>
</tr>
<tr style="background-color:#f6f8fa;">
<td style="font-family:Arial,sans-serif;font-size:12px;color:#586069;padding:6px 8px;border:1px solid #e1e4e8;">Date</td>
<td style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border:1px solid #e1e4e8;">April 18, 2026</td>
</tr>
<tr>
<td style="font-family:Arial,sans-serif;font-size:12px;color:#586069;padding:6px 8px;border:1px solid #e1e4e8;">Card</td>
<td style="font-family:Arial,sans-serif;font-size:13px;padding:6px 8px;border:1px solid #e1e4e8;">Theo Mbeki &bull;&bull;&bull;&bull; 4821</td>
</tr>
</table>

<p style="font-size:13px;color:#586069;">This transaction is awaiting categorization. Please add a business purpose and category within 7 days to stay in compliance with Ellery's expense policy.</p>

<p>
<a href="#" style="background-color:#131313;color:#ffffff;padding:8px 20px;font-family:Arial,sans-serif;font-size:13px;text-decoration:none;">Categorize now</a>
</p>

</td></tr>
<tr><td style="background-color:#f9fafb;padding:12px 20px;text-align:center;font-family:Arial,sans-serif;font-size:11px;color:#888888;">
Ramp &bull; <a href="#" style="color:#888888;">Expense policy</a> &bull; <a href="#" style="color:#888888;">Unsubscribe</a>
</td></tr>
</table>
