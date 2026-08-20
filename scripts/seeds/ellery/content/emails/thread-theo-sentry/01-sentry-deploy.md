---
key: theo-sentry-01-sentry-deploy
model: EmailMessage
thread: !ref thread-theo-sentry
user: !ref theo
message_type: received
sender: "Sentry <alerts@sentry.io>"
to:
  - !ref theo
subject: "Deploy #481 — stable, 2 warnings"
received_at: !relative_day {offset: -1, hour: 11, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">
<tr><td style="background-color:#362d59;padding:16px 20px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">Sentry</span>
<span style="color:#9b8fc7;font-family:Arial,sans-serif;font-size:13px;margin-left:8px;">Release Tracking</span>
</td></tr>
<tr><td style="padding:20px;font-family:Arial,sans-serif;font-size:14px;color:#1d1d1d;">

<p>
<span style="background-color:#2da44e;color:#ffffff;padding:2px 8px;border-radius:2px;font-family:Arial,sans-serif;font-size:12px;font-weight:bold;">STABLE</span>
&nbsp; <strong>app@2.14.4</strong> &bull; Deploy #481
</p>

<table width="100%" cellpadding="4" cellspacing="0" style="border-collapse:collapse;margin:12px 0;font-size:13px;">
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;width:130px;">Deployed at</td><td style="padding:6px 8px;">Today, 10:42 AM ET</td></tr>
<tr><td style="padding:6px 8px;color:#586069;">Environment</td><td style="padding:6px 8px;">production</td></tr>
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;">Commits</td><td style="padding:6px 8px;">4 commits by theo-mbeki</td></tr>
<tr><td style="padding:6px 8px;color:#586069;">New issues</td><td style="padding:6px 8px;color:#e36209;">2 warnings</td></tr>
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;">Resolved issues</td><td style="padding:6px 8px;color:#2da44e;">3 resolved</td></tr>
</table>

<p style="font-size:13px;font-weight:bold;margin-bottom:8px;">New warnings in this deploy:</p>
<ul style="font-family:Courier New,monospace;font-size:12px;margin:0;padding-left:16px;">
<li style="margin-bottom:4px;">ReactDOM: Warning — missing key prop in diff hunk list (ReviewPanel.tsx:142)</li>
<li>Console warning — localStorage quota nearing limit on large contracts (diffStore.ts:88)</li>
</ul>

<p>
<a href="#" style="background-color:#6c5fc7;color:#ffffff;padding:8px 16px;font-family:Arial,sans-serif;font-size:13px;text-decoration:none;">View release</a>
</p>

</td></tr>
<tr><td style="background-color:#f9fafb;padding:12px 20px;text-align:center;font-family:Arial,sans-serif;font-size:11px;color:#888888;">
Sentry &bull; <a href="#" style="color:#888888;">Notification settings</a> &bull; <a href="#" style="color:#888888;">Unsubscribe</a>
</td></tr>
</table>
