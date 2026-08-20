---
key: msg-priya-eng-newsletter-infrabrief
model: EmailMessage
thread: !ref thread-priya-eng-newsletter
user: !ref priya
message_type: received
sender: "InfraBrief <weekly@infrabrief.io>"
to:
  - !ref priya
subject: "This Week in Infra — April 19, 2026"
received_at: !relative_day {offset: -2, hour: 6, tz: America/New_York}
labels: [inbox, unread]
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;">
<tr><td style="background-color:#18181b;padding:20px 24px;">
<span style="color:#22d3ee;font-family:Courier New,monospace;font-size:20px;font-weight:bold;">InfraBrief</span>
<br><span style="color:#71717a;font-family:Arial,sans-serif;font-size:12px;">Cloud · Reliability · Platform Engineering &bull; Issue #184</span>
</td></tr>

<tr><td style="padding:24px;font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;">

<p style="font-family:Courier New,monospace;font-size:16px;color:#18181b;"><strong>AWS KMS Cross-Region: What Actually Happens</strong></p>
<p>A thread from an AWS Principal Engineer went around this week clarifying what "cross-region KMS API calls" actually means for data locality compliance. Short version: the key material never leaves the region where the CMK was created. Only the cryptographic request metadata (which key, what operation) crosses regions. Whether this satisfies GDPR data residency obligations depends on whether your legal team considers key request metadata to be personal data — most DPAs don't, but some EU supervisory authorities have taken expansive positions. Recommended: get an opinion from a GDPR specialist before making customer-facing commitments.</p>

<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">

<p style="font-family:Courier New,monospace;font-size:16px;color:#18181b;"><strong>RDS Connection Pool Sizing at Scale</strong></p>
<p>A well-sourced post this week on the canonical RDS connection pool mistake: setting pool size based on how many connections you expect, rather than how many your database can efficiently handle. For PostgreSQL on a db.t3.medium, the sweet spot is typically 15-25 connections per app instance, regardless of app concurrency. Above that, you're queueing at the DB layer rather than the app layer, which makes the latency problem invisible until it's severe. The fix: explicit pool size caps plus connection wait timeouts that surface the problem to callers rather than silently degrading.</p>

<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">

<p style="font-family:Courier New,monospace;font-size:16px;color:#18181b;"><strong>Terraform Provider for AWS: v5.45 Notable Changes</strong></p>
<p>The AWS Terraform provider v5.45 includes changes to the <span style="font-family:Courier New,monospace;font-size:13px;background-color:#f4f4f5;padding:2px 4px;">aws_s3_bucket</span> resource that affect bucket ownership controls. If you have existing buckets managed with ACLs, review the migration guide before upgrading. Several teams reported unexpected plan diffs after upgrading without reading the changelog.</p>

<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">

<p style="font-family:Courier New,monospace;font-size:15px;color:#18181b;"><strong>Jobs</strong></p>
<p style="font-size:13px;color:#555;">Highlighted this week: Relay Networks (Series B) looking for SRE with Kubernetes + observability depth. Remotive listing shows remote-US.</p>
</td></tr>

<tr><td style="background-color:#f4f4f5;padding:12px 24px;text-align:center;font-family:Courier New,monospace;font-size:11px;color:#666666;">
InfraBrief &bull; <a href="#" style="color:#18181b;">Manage preferences</a> &bull; <a href="#" style="color:#18181b;">Unsubscribe</a>
</td></tr>
</table>
