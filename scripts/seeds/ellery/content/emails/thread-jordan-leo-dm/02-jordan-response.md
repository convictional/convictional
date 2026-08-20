---
key: jordan-leo-dm-02-jordan-response
model: EmailMessage
thread: !ref thread-jordan-leo-dm
user: !ref jordan
message_type: sent
sender: !ref jordan
to:
  - !ref leo
subject: "Re: Prototype flag for Pam's team"
received_at: !relative_day {offset: -3, hour: 9, tz: America/New_York}
---
<p>Leo,</p>

<p>Done — flag is enabled for Ipso Wakely. Their users will see the prototype banner in the review panel.</p>

<p>On your questions:</p>

<p><strong>Rate limiting:</strong> There is a soft limit — 20 suggestions/minute per user. For a 3-lawyer team doing a real NDA that should be plenty. If they hit it the UI degrades gracefully (suggestions queue, no error shown). I'll watch the logs Thursday morning in case something unexpected happens.</p>

<p><strong>Disclaimer:</strong> That was a bug in the flag rollout — I pushed a fix yesterday. The disclaimer now shows for all prototype-flag users. Emma should double-check in the session, but it should be there. The exact text is: "AI-generated suggestion — verify against your playbook before accepting."</p>

<p>One heads-up: the prototype is on our <em>current</em> eval model, not the improved version I've been training. That means quality is roughly 0.68 on the benchmark — good enough for a research session, not good enough to show as the real thing. Please make sure Pam knows she's seeing v0.</p>

<p>Jordan</p>
