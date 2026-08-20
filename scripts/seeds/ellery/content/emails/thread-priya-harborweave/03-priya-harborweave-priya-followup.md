---
key: msg-priya-harborweave-priya-followup
model: EmailMessage
thread: !ref thread-priya-harborweave
user: !ref priya
message_type: sent
sender: !ref priya
to:
  - "Ivan Ostrowski <ivan@harborweave.com>"
subject: "Re: EU region-scoped storage eval — Ellery"
sent_at: !relative_day {offset: -4, hour: 9, tz: America/New_York}
in_reply_to: !ref thread-priya-harborweave-msg-priya-harborweave-ivan-response
---
<p>Ivan,</p>

<p>The key management detail is exactly what I needed. My read: the cross-region KMS API call is acceptable for our use case — the customer's concern is about data residency, not key residency, and the AWS backbone is not the same as data leaving the EU. I'll confirm that interpretation with Maren and our outside counsel before we commit.</p>

<p>Yes, the GDPR audit reference would be useful. Can you make an intro by end of this week? I'd prefer a brief technical conversation rather than a formal reference call — just want to understand the implementation path they followed.</p>

<p>Priya</p>
