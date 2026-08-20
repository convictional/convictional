---
key: msg-priya-doug-doug-questions
model: EmailMessage
thread: !ref thread-priya-doug
user: !ref priya
message_type: received
sender: "Doug Rennert <doug.rennert@keatingmarsh.com>"
to:
  - !ref priya
subject: "Follow-up: security questionnaire Q44-Q51"
received_at: !relative_day {offset: -4, hour: 14, tz: America/New_York}
labels: [inbox]
---
<p>Priya,</p>

<p>Thanks for the partial submission last week. I've reviewed Q1-Q43 and most of them are answered adequately. Before we proceed, I need clarity on Q44-Q51, which covers your incident response and breach notification posture. My CISO-level review always focuses hardest on this section because it tells me how a vendor actually behaves when something goes wrong, not just how their controls are designed.</p>

<p>Specific gaps:</p>

<p><strong>Q44 (Mean time to detect):</strong> Your answer references PagerDuty alerting but doesn't give me an actual MTTD number. What was your average MTTD for security-relevant events in the past 12 months?</p>

<p><strong>Q47 (Customer notification timeline):</strong> You said "within 72 hours of confirmed breach." That's the minimum under GDPR. But my question asked: what's your internal threshold for triggering customer notification? If you detect a potential breach on day 0 and spend 71 hours confirming it before notifying, you've technically complied but I haven't had time to respond. What's your actual practice?</p>

<p><strong>Q49 (Forensic retention):</strong> Do you retain system logs sufficient for forensic investigation after a security incident? What's the retention window, and where are logs stored?</p>

<p><strong>Q51 (Tabletop exercises):</strong> Has your team conducted a tabletop incident response exercise in the past 12 months? If yes, who participated and what were the findings?</p>

<p>These aren't gotcha questions — I want to understand how your team thinks about incidents, not just check a box. Happy to get on a call if the written responses are getting complicated.</p>

<p>Doug Rennert<br>
<em>CISO, Keating &amp; Marsh LLP</em></p>
