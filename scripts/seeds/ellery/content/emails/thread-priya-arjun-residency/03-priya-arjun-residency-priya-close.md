---
key: msg-priya-arjun-residency-priya-close
model: EmailMessage
thread: !ref thread-priya-arjun-residency
user: !ref priya
message_type: sent
sender: !ref priya
to:
  - !ref arjun
subject: "Re: Region-scoped storage — follow-up from the ADR"
sent_at: !relative_day {offset: -1, hour: 13, tz: America/New_York}
in_reply_to: !ref thread-priya-arjun-residency-msg-priya-arjun-residency-arjun-confirm
---
<p>Arjun,</p>

<p>Good. Log the RDS provisioning risk in the ADR and let me know if it manifests. I'll get the key management answer by Monday.</p>

<p>One more thing: please write down the tenant-level routing decision in the ADR as an explicit choice with the reasoning. "Document-level classification is a future scope item" is exactly the kind of decision that disappears unless it's written. I want to be able to point to it when someone asks in six months.</p>

<p>Priya</p>
