---
key: theo-github-01-github-pr-approved
model: EmailMessage
thread: !ref thread-theo-github
user: !ref theo
message_type: received
sender: "GitHub <notifications@github.com>"
to:
  - !ref theo
subject: "[ellery/app] Your PR was approved"
received_at: !relative_day {offset: -2, hour: 15, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">
<tr><td style="background-color:#24292e;padding:16px 20px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">GitHub</span>
</td></tr>
<tr><td style="padding:20px;font-family:Arial,sans-serif;font-size:14px;color:#24292e;">

<p>
<span style="background-color:#2da44e;color:#ffffff;padding:2px 8px;border-radius:2px;font-family:Arial,sans-serif;font-size:12px;font-weight:bold;">Approved</span>
&nbsp; <strong>ellery/app</strong> — Pull Request #891
</p>

<p style="font-size:15px;"><strong>feat: inline accept/reject controls in diff view</strong></p>

<p><strong>emma-lindqvist</strong> approved this pull request</p>

<p style="background-color:#f6f8fa;padding:12px;border:1px solid #e1e4e8;border-radius:4px;font-family:Arial,sans-serif;font-size:13px;">
&ldquo;Tested in the research build — this is exactly right. The lawyers in session 4 would have found this immediately. Shipping this before Thursday.&rdquo;
</p>

<table width="100%" cellpadding="4" cellspacing="0" style="border-collapse:collapse;margin:12px 0;font-size:13px;">
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;width:100px;">Branch</td><td style="padding:6px 8px;font-family:Courier New,monospace;font-size:12px;">feat/inline-accept-reject</td></tr>
<tr><td style="padding:6px 8px;color:#586069;">CI status</td><td style="padding:6px 8px;"><span style="color:#2da44e;">&#10003;</span> All checks passed (11/11)</td></tr>
<tr style="background-color:#f6f8fa;"><td style="padding:6px 8px;color:#586069;">Reviewers</td><td style="padding:6px 8px;">emma-lindqvist (approved), arjun-mehta (approved)</td></tr>
</table>

<p style="font-size:13px;color:#586069;">You're receiving this because you authored this pull request.</p>
<p><a href="#" style="color:#0366d6;font-size:13px;">View pull request</a> &bull; <a href="#" style="color:#0366d6;font-size:13px;">Merge</a> &bull; <a href="#" style="color:#0366d6;font-size:13px;">Unsubscribe</a></p>
</td></tr>
</table>
