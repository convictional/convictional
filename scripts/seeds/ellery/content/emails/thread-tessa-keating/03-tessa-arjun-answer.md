---
key: msg-tessa-arjun-answer
model: EmailMessage
thread: !ref thread-tessa-keating
user: !ref tessa
message_type: sent
sender: !ref tessa
to:
  - "Amira Saleh <amira.saleh@keatingmarsh.com>"
subject: "Re: Pilot proposal — revisions"
sent_at: !relative_day {offset: -1, hour: 10, tz: America/New_York}
in_reply_to: !ref thread-tessa-keating-msg-amira-reply
---
<p>Amira,</p>

<p>Got the answer from Arjun on key management. Two sentences as requested:</p>

<p><em>Root keys for the EU region are held in AWS KMS within eu-west-1, owned exclusively by Ellery infrastructure. Rotation policy is 365 days with immediate rotation capability on customer request; access logs are captured in CloudTrail and available to SOC 2 auditors.</em></p>

<p>Thursday 2pm ET is confirmed on our side — Darren and I will be on the call. If it would be helpful to also have Arjun available for any remaining technical questions, let me know and I'll pull him in.</p>

<p>On the SOC 2 draft: our auditor (Halden &amp; Rossi) is targeting a draft evidence package by day 1.5 weeks. I'll send it to you as soon as it comes through.</p>

<p>Tessa</p>
