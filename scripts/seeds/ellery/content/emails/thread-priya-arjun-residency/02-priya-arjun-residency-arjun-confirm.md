---
key: msg-priya-arjun-residency-arjun-confirm
model: EmailMessage
thread: !ref thread-priya-arjun-residency
user: !ref priya
message_type: received
sender: !ref arjun
to:
  - !ref priya
subject: "Re: Region-scoped storage — follow-up from the ADR"
received_at: !relative_day {offset: -1, hour: 11, tz: America/New_York}
in_reply_to: !ref thread-priya-arjun-residency-msg-priya-arjun-residency-priya-note
labels: [inbox, unread]
---
<p>Priya,</p>

<ol>
<li><strong>Routing.</strong> Confirmed — tenant-level classification is what I'm building. The only case where document-level might matter is if a single tenant has mixed-jurisdiction data, but none of our current customers or Keating have asked for that. I'll add a note to the ADR flagging this as a future scope item if it comes up.</li>
<li><strong>Key management.</strong> Holding. I'll use a placeholder approach (same-region KMS, no cross-region calls) in staging so we can test the routing independently. The key management pattern is a one-day implementation change once we have the green light.</li>
<li><strong>Timeline.</strong> Three weeks to staging is tight but realistic, assuming the key management question is resolved in week one and there are no surprises in the EU fleet provisioning. I have some concerns about the time it takes to provision RDS in eu-central-1 — Terraform says 15-20 minutes but I've seen it take longer in that region. I'm tracking that as a risk.</li>
</ol>

<p>Arjun</p>
