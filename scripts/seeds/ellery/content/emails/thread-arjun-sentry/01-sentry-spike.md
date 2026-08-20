---
key: arjun-sentry-01-sentry-spike
model: EmailMessage
thread: !ref thread-arjun-sentry
user: !ref arjun
message_type: received
sender: "Sentry <alerts@sentry.io>"
to:
  - !ref arjun
subject: "New error spike: ExtractionService timeout"
received_at: !relative_day {offset: 0, hour: 7, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">
<tr><td style="background-color:#362d59;padding:16px 20px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">Sentry</span>
<span style="color:#9b8fc7;font-family:Arial,sans-serif;font-size:13px;margin-left:8px;">Error Monitoring</span>
</td></tr>
<tr><td style="padding:20px;font-family:Arial,sans-serif;font-size:14px;color:#1d1d1d;">

<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:12px;margin-bottom:16px;">
<tr>
<td style="padding:10px 12px;">
<span style="color:#856404;font-family:Arial,sans-serif;font-size:13px;font-weight:bold;">ERROR SPIKE</span>
<span style="background-color:#dc3545;color:#ffffff;padding:2px 6px;border-radius:2px;font-family:Arial,sans-serif;font-size:11px;margin-left:8px;">UNRESOLVED</span>
</td>
</tr>
</table>

<p><strong>ExtractionService — ReadTimeout</strong></p>
<p style="font-family:Courier New,monospace;background-color:#f6f8fa;padding:8px 12px;border-radius:4px;font-size:12px;border-left:3px solid #dc3545;">
requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='extraction-worker.ellery.internal', port=8443): Read timed out. (read timeout=30)
</p>

<table width="100%" cellpadding="4" cellspacing="0" style="border-collapse:collapse;margin:12px 0;font-size:13px;">
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;width:130px;">Environment</td><td style="padding:6px 8px;">production</td></tr>
<tr><td style="padding:6px 8px;color:#586069;">Occurrences</td><td style="padding:6px 8px;font-weight:bold;color:#dc3545;">47 in the last hour</td></tr>
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;">Affected users</td><td style="padding:6px 8px;">12</td></tr>
<tr><td style="padding:6px 8px;color:#586069;">First seen</td><td style="padding:6px 8px;">Today, 06:51 AM ET</td></tr>
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;">Release</td><td style="padding:6px 8px;font-family:Courier New,monospace;font-size:12px;">platform@2.14.3</td></tr>
</table>

<p style="font-size:13px;color:#586069;">This event has been assigned to <strong>arjun@ellery.ai</strong> based on ownership rules.</p>

<p>
<a href="#" style="background-color:#6c5fc7;color:#ffffff;padding:8px 16px;font-family:Arial,sans-serif;font-size:13px;text-decoration:none;">View in Sentry</a>
&nbsp;
<a href="#" style="color:#6c5fc7;font-family:Arial,sans-serif;font-size:13px;">Resolve</a>
&nbsp;
<a href="#" style="color:#6c5fc7;font-family:Arial,sans-serif;font-size:13px;">Ignore</a>
</p>

</td></tr>
<tr><td style="background-color:#f9fafb;padding:12px 20px;text-align:center;font-family:Arial,sans-serif;font-size:11px;color:#888888;">
Sentry &bull; <a href="#" style="color:#888888;">Notification settings</a> &bull; <a href="#" style="color:#888888;">Unsubscribe</a>
</td></tr>
</table>
