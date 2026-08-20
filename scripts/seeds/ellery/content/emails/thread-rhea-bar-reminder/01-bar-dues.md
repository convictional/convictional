---
key: msg-rhea-bar-reminder-bar-dues
model: EmailMessage
thread: !ref thread-rhea-bar-reminder
user: !ref rhea
message_type: received
sender: "NY State Bar <noreply@nysba.org>"
to:
  - !ref rhea
subject: "Bar dues payment reminder — balance due by May 31"
received_at: !relative_day {offset: -4, hour: 6, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,Helvetica,sans-serif;">
<tr>
  <td style="background-color:#003366;padding:20px 24px;">
    <span style="color:#ffffff;font-size:18px;font-weight:bold;">New York State Bar Association</span>
  </td>
</tr>
<tr>
  <td style="padding:24px;background-color:#ffffff;color:#333333;font-size:14px;line-height:1.6;">
    <p style="margin-top:0;">Dear Rhea Patel,</p>

    <p>This is a reminder that your annual bar dues are due by <strong>May 31, 2026</strong>. Failure to pay by the due date will result in suspension of your membership and removal from the New York State attorney registry.</p>

    <table width="100%" cellpadding="10" cellspacing="0" style="border:1px solid #e0e0e0;margin:16px 0;">
      <tr style="background-color:#f5f5f5;">
        <td style="font-weight:bold;">Member Name</td>
        <td>Rhea Patel</td>
      </tr>
      <tr>
        <td style="font-weight:bold;">Registration Number</td>
        <td>5841923</td>
      </tr>
      <tr style="background-color:#f5f5f5;">
        <td style="font-weight:bold;">Amount Due</td>
        <td><strong>$375.00</strong></td>
      </tr>
      <tr>
        <td style="font-weight:bold;">Due Date</td>
        <td>May 31, 2026</td>
      </tr>
    </table>

    <p>Pay online through the NYSBA member portal using a credit card or ACH transfer. You may also mail a check payable to "New York State Bar Association" to the address below.</p>

    <p style="text-align:center;margin:16px 0;">
      <a href="#" style="background-color:#003366;color:#ffffff;padding:10px 20px;text-decoration:none;font-size:13px;font-weight:bold;">Pay Now</a>
    </p>

    <p style="font-size:12px;color:#888888;margin-top:24px;">New York State Bar Association · One Elk Street · Albany, NY 12207<br>
    This is an automated message. Do not reply to this email.</p>
  </td>
</tr>
</table>
