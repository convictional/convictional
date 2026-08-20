---
key: msg-priya-soc2-brandt-clarify
model: EmailMessage
thread: !ref thread-priya-soc2
user: !ref priya
message_type: received
sender: "Brandt Soh <brandt.soh@haldenrossi.com>"
to:
  - !ref priya
subject: "Re: Audit scope and timeline — Ellery SOC 2 Type I"
received_at: !relative_day {offset: -3, hour: 10, tz: America/New_York}
in_reply_to: !ref thread-priya-soc2-msg-priya-soc2-priya-response
labels: [inbox]
---
<p>Priya,</p>

<p>Appreciated — this is exactly the level of detail I need.</p>

<p>On MFA evidence: an audit log showing enrolled users is stronger than a policy screenshot, but either is defensible for a Type I opinion. If you can provide both, do it. If the audit log requires exporting from your IDP and you'd rather not expose it, the policy screenshot plus a signed attestation from you is acceptable.</p>

<p>Converting the deploy automation account to short-lived tokens is the right call and I note it favorably in my assessment. The pattern of fixing the underlying issue rather than documenting a compensating control is exactly what a mature security posture looks like — it'll serve you well when you go for Type II.</p>

<p>Looking good overall. The May 5 evidence deadline still works — let me know if anything slips.</p>

<p>Brandt</p>
