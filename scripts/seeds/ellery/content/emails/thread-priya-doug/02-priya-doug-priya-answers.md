---
key: msg-priya-doug-priya-answers
model: EmailMessage
thread: !ref thread-priya-doug
user: !ref priya
message_type: sent
sender: !ref priya
to:
  - "Doug Rennert <doug.rennert@keatingmarsh.com>"
subject: "Re: Follow-up: security questionnaire Q44-Q51"
sent_at: !relative_day {offset: -3, hour: 16, tz: America/New_York}
in_reply_to: !ref thread-priya-doug-msg-priya-doug-doug-questions
---
<p>Doug,</p>

<p>I prefer the written format — it forces precision. Let me answer each one directly.</p>

<p><strong>Q44 (MTTD):</strong> Our trailing 12-month average MTTD for security-relevant alerts is 4.2 minutes. The distribution is bimodal: most alerts resolve in under 2 minutes (automated); the outliers (>15 minutes) are all during low-traffic windows when on-call response is slower. I'll include the PagerDuty report showing this distribution in the evidence package.</p>

<p><strong>Q47 (Customer notification threshold):</strong> Fair challenge. Our written policy says 72 hours post-confirmation. Our actual practice is: if we assess a potential breach at medium or high severity, we notify account contacts within 24 hours of <em>detection</em>, even if confirmation is pending. The notification language in that case is explicit that it's precautionary and may be downgraded. We've done this once in our operating history and it turned out to be a false positive — the customer later told us they were glad we notified early. I'll add this to our written IR policy before the evidence submission.</p>

<p><strong>Q49 (Forensic retention):</strong> System logs are retained for 365 days in S3 with 90-day hot storage in CloudWatch. Application-level logs are retained for 90 days. We use a separate security-event log stream with 2-year retention for authentication events, privilege changes, and data access events. These are stored in an append-only S3 bucket with object lock.</p>

<p><strong>Q51 (Tabletop exercises):</strong> We ran a tabletop exercise in February 2026, seven participants including myself, Arjun, and our on-call rotation. Scenario: credential compromise via phishing on a privileged account. Findings: our revocation procedure had a gap — we couldn't revoke active API keys without a 15-minute propagation delay. We've since implemented a centralized secrets rotation endpoint that reduces that to under 60 seconds. I can provide the tabletop summary document.</p>

<p>Happy to get on a 30-minute call if you want to walk through any of this. I'd rather you come away confident than come away with open questions you haven't asked.</p>

<p>Priya<br>
<em>CTO, Ellery</em></p>
