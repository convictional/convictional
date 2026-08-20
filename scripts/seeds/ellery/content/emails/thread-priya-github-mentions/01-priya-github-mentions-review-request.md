---
key: msg-priya-github-mentions-review-request
model: EmailMessage
thread: !ref thread-priya-github-mentions
user: !ref priya
message_type: received
sender: "GitHub <notifications@github.com>"
to:
  - !ref priya
subject: "[ellery/platform] Review requested on PR #2413 — EU storage routing"
received_at: !relative_day {offset: 0, hour: 7, tz: America/New_York}
labels: [inbox, unread]
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">
<tr><td style="background-color:#24292f;padding:18px 24px;">
<span style="color:#ffffff;font-family:Arial,sans-serif;font-size:18px;font-weight:bold;">GitHub</span>
</td></tr>
<tr><td style="padding:20px 24px;font-family:Arial,sans-serif;font-size:14px;color:#24292f;">
<p style="font-size:15px;font-weight:bold;margin-top:0;">Review requested on pull request</p>

<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d0d7de;border-radius:6px;margin:12px 0;">
<tr><td style="padding:16px;">
<p style="margin:0 0 6px;"><strong>
<a href="#" style="color:#0969da;text-decoration:none;">ellery/platform</a>
</strong></p>
<p style="margin:0 0 8px;font-size:15px;">
<a href="#" style="color:#0969da;text-decoration:none;font-weight:bold;">#2413 — feat: tenant-level EU region routing and storage isolation</a>
</p>
<p style="margin:0;font-size:13px;color:#57606a;">Opened by <strong>arjun</strong> &bull; +487 lines, −23 lines &bull; 4 files changed</p>
</td></tr>
</table>

<p><strong>arjun</strong> requested your review on this pull request.</p>

<p style="font-size:13px;color:#57606a;background-color:#f6f8fa;padding:12px;border-left:3px solid #d0d7de;">
Implements tenant-level EU region routing. When a tenant's <span style="font-family:Courier New,monospace;background-color:#eee;padding:1px 4px;">data_region</span> field is set to <span style="font-family:Courier New,monospace;background-color:#eee;padding:1px 4px;">"eu"</span>, contract storage and retrieval operations are routed to eu-west-1 S3 bucket and RDS instance. Key management uses same-region KMS CMK (cross-region approach held pending legal confirmation). Includes routing middleware, tenant model field, and migration. Tests passing.
</p>

<p><strong>Files changed:</strong></p>
<ul style="font-family:Courier New,monospace;font-size:13px;color:#333;">
<li>app/models/tenant.py (+12 lines)</li>
<li>app/middleware/region_router.py (+198 lines)</li>
<li>app/storage/s3_client.py (+89 lines)</li>
<li>migrations/versions/0047_add_tenant_data_region.py (+188 lines)</li>
</ul>

<p style="text-align:center;margin-top:20px;">
<span style="background-color:#1f883d;color:#ffffff;padding:10px 24px;font-size:13px;">View pull request</span>
</p>
</td></tr>
<tr><td style="background-color:#f6f8fa;padding:12px 24px;text-align:center;font-family:Arial,sans-serif;font-size:11px;color:#57606a;">
You're receiving this because you were requested to review this pull request &bull; <a href="#" style="color:#57606a;">Manage notifications</a>
</td></tr>
</table>
