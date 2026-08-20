---
key: msg-priya-pagerduty-resolved
model: EmailMessage
thread: !ref thread-priya-pagerduty
user: !ref priya
message_type: received
sender: "PagerDuty <noreply@pagerduty.com>"
to:
  - !ref priya
subject: "[RESOLVED] minor-latency-spike-april-19 — resolved in 14m"
received_at: !relative_day {offset: -1, hour: 3, tz: America/New_York}
labels: [inbox, unread]
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">
<tr><td style="background-color:#06ac38;padding:16px 24px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:18px;font-weight:bold;">&#10003; Incident Resolved</span>
</td></tr>
<tr><td style="padding:20px 24px;font-family:Arial,sans-serif;font-size:14px;color:#333333;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr>
<td width="140" style="font-weight:bold;color:#555;padding:4px 0;">Incident:</td>
<td style="padding:4px 0;"><span style="font-family:Courier New,monospace;font-size:13px;">minor-latency-spike-april-19</span></td>
</tr>
<tr>
<td style="font-weight:bold;color:#555;padding:4px 0;">Service:</td>
<td style="padding:4px 0;">ellery-platform / contract-ingestion</td>
</tr>
<tr>
<td style="font-weight:bold;color:#555;padding:4px 0;">Severity:</td>
<td style="padding:4px 0;"><span style="background-color:#fef3c7;color:#92400e;padding:2px 8px;border-radius:3px;font-size:12px;">P3 — Minor</span></td>
</tr>
<tr>
<td style="font-weight:bold;color:#555;padding:4px 0;">Triggered:</td>
<td style="padding:4px 0;">April 19, 2026 at 02:21 AM ET</td>
</tr>
<tr>
<td style="font-weight:bold;color:#555;padding:4px 0;">Resolved:</td>
<td style="padding:4px 0;">April 19, 2026 at 02:35 AM ET</td>
</tr>
<tr>
<td style="font-weight:bold;color:#555;padding:4px 0;">Duration:</td>
<td style="padding:4px 0;"><strong>14 minutes</strong></td>
</tr>
<tr>
<td style="font-weight:bold;color:#555;padding:4px 0;">Acknowledged by:</td>
<td style="padding:4px 0;">arjun@ellery.ai (2m 04s response time)</td>
</tr>
<tr>
<td style="font-weight:bold;color:#555;padding:4px 0;">Resolution note:</td>
<td style="padding:4px 0;">RDS connection pool saturation during batch ingestion job. Increased pool limit from 20 to 35. Monitoring for recurrence.</td>
</tr>
</table>

<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">

<p><strong>Alert timeline</strong></p>
<table width="100%" cellpadding="4" cellspacing="0" style="font-size:12px;">
<tr>
<td style="color:#57606a;width:90px;">02:21 AM</td>
<td>P95 latency exceeded 800ms threshold (contract-ingestion service)</td>
</tr>
<tr>
<td style="color:#57606a;">02:23 AM</td>
<td>Arjun Mehta acknowledged</td>
</tr>
<tr>
<td style="color:#57606a;">02:31 AM</td>
<td>Root cause identified: connection pool exhaustion</td>
</tr>
<tr>
<td style="color:#57606a;">02:35 AM</td>
<td>Resolved — latency returned to baseline (P95 &lt;180ms)</td>
</tr>
</table>
</td></tr>
<tr><td style="background-color:#f6f8fa;padding:12px 24px;text-align:center;font-family:Arial,sans-serif;font-size:11px;color:#57606a;">
PagerDuty &bull; You're receiving this because you're on the ellery-platform on-call schedule &bull; <a href="#" style="color:#57606a;">Manage notifications</a>
</td></tr>
</table>
