---
key: msg-kai-research-reply
model: EmailMessage
thread: !ref thread-leo-kai-research
user: !ref leo
message_type: received
sender: "Kai Andersen <kai.andersen@corvuslegal.com>"
to:
  - !ref leo
subject: "Re: Research session on Tuesday?"
received_at: !relative_day {offset: -3, hour: 9, tz: America/New_York}
in_reply_to: !ref thread-leo-kai-research-msg-leo-kai-session
labels: [inbox]
---
<p>Leo,</p>

<p>Tuesday afternoon works — 2pm ET. I'll bring Marcus Lee (our primary reviewer on vendor MSAs for the last six months; he has opinions).</p>

<p>One heads-up: we had a situation last week where the playbook suggestion on a limitation-of-liability clause was subtly wrong — pulled in a provision from a different contract type. Not a blocker, but I want to make sure that kind of failure mode is on Emma's research radar. It's exactly what matters at our scale.</p>

<p>Kai<br>
<em>Deputy GC, Corvus Legal</em></p>
