---
key: arjun-github-01-github-pr-approved
model: EmailMessage
thread: !ref thread-arjun-github
user: !ref arjun
message_type: received
sender: "GitHub <notifications@github.com>"
to:
  - !ref arjun
subject: "[ellery/platform] PR #2418 approved, tests green"
received_at: !relative_day {offset: -2, hour: 14, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">
<tr><td style="background-color:#24292e;padding:16px 20px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">GitHub</span>
</td></tr>
<tr><td style="padding:20px;font-family:Arial,sans-serif;font-size:14px;color:#24292e;">

<p>
<span style="background-color:#2da44e;color:#ffffff;padding:2px 8px;border-radius:2px;font-family:Arial,sans-serif;font-size:12px;font-weight:bold;">Approved</span>
&nbsp; <strong>ellery/platform</strong> — Pull Request #2418
</p>

<p style="font-size:15px;"><strong>feat: add tenant-scoped routing middleware for EU region</strong></p>

<p><strong>jordan-reyes</strong> approved this pull request</p>

<p style="background-color:#f6f8fa;padding:12px;border:1px solid #e1e4e8;border-radius:4px;font-family:Arial,sans-serif;font-size:13px;">
&ldquo;Nice. The cache fallback is clean. Left one minor comment on the log level — use <span style="font-family:Courier New,monospace;">WARNING</span> not <span style="font-family:Courier New,monospace;">ERROR</span> for the fallback path so we don't spam PagerDuty on a brief DB hiccup. Otherwise LGTM.&rdquo;
</p>

<table width="100%" cellpadding="4" cellspacing="0" style="border-collapse:collapse;margin:12px 0;font-size:13px;">
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;width:100px;">Branch</td><td style="padding:6px 8px;font-family:Courier New,monospace;font-size:12px;">feat/eu-routing-middleware</td></tr>
<tr><td style="padding:6px 8px;color:#586069;">CI status</td><td style="padding:6px 8px;"><span style="color:#2da44e;">&#10003;</span> All checks passed (14/14)</td></tr>
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;">Reviewers</td><td style="padding:6px 8px;">jordan-reyes (approved), theo-mbeki (approved)</td></tr>
</table>

<p style="font-size:13px;color:#586069;">You're receiving this because you authored this pull request.</p>
<p><a href="#" style="color:#0366d6;font-size:13px;">View pull request</a> &bull; <a href="#" style="color:#0366d6;font-size:13px;">Merge</a> &bull; <a href="#" style="color:#0366d6;font-size:13px;">Unsubscribe</a></p>
</td></tr>
</table>
