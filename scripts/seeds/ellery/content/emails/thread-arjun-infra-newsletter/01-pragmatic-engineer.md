---
key: arjun-infra-newsletter-01-pragmatic-engineer
model: EmailMessage
thread: !ref thread-arjun-infra-newsletter
user: !ref arjun
message_type: received
sender: "The Pragmatic Engineer <weekly@pragmaticengineer.com>"
to:
  - !ref arjun
subject: "The Pragmatic Engineer Weekly"
received_at: !relative_day {offset: -2, hour: 8, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,sans-serif;">
<tr><td style="background-color:#1a1a2e;padding:20px 24px;">
<span style="color:#ffffff;font-size:18px;font-weight:bold;">The Pragmatic Engineer</span>
<span style="color:#a0a0c0;font-size:13px;display:block;margin-top:4px;">Weekly Newsletter</span>
</td></tr>
<tr><td style="padding:24px;color:#1d1d1d;font-size:14px;">

<p>Welcome to this week's issue. This week: platform team structures at scale, and why "platform engineering" means something different depending on company stage.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<h2 style="font-family:Georgia,serif;font-size:18px;color:#1a1a2e;">How Platform Teams Form (And Break) at Series A</h2>
<p>Most Series A companies don't have a platform team — they have one or two engineers who reluctantly own infra because they're the only ones who understand it. This is fine until it isn't. The tell: when the cost of a new service is mostly coordination overhead rather than engineering work.</p>
<p>The pattern I see working: designate someone explicitly as the infra owner before the team needs it, not after the first production outage. Give them a week of protected time per sprint. Don't make them the hero — make them the enabler.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<h2 style="font-family:Georgia,serif;font-size:18px;color:#1a1a2e;">On Multi-Region: When You Actually Need It</h2>
<p>Multi-region is one of those things engineers over-engineer in year one and under-engineer in year three. The rule of thumb I'd use: if a customer contractually requires data residency in a specific geography, you need it. If you're doing it for latency, measure first — most B2B SaaS companies have all their customers in the same three cities.</p>
<p>For the data-residency use case specifically, envelope encryption with region-scoped KMS keys is usually the right design. Don't replicate more than you must.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<p style="font-size:12px;color:#888888;">The Pragmatic Engineer &bull; <a href="#" style="color:#888888;">Manage preferences</a> &bull; <a href="#" style="color:#888888;">Unsubscribe</a></p>
</td></tr>
</table>
