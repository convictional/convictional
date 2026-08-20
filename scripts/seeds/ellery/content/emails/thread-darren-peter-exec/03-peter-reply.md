---
key: msg-peter-reply
model: EmailMessage
thread: !ref thread-darren-peter-exec
user: !ref darren
message_type: received
sender: "Peter Nakagawa <peter.nakagawa@keatingmarsh.com>"
to:
  - !ref darren
cc:
  - !ref tessa
  - !ref maren
subject: "Re: Post-demo follow-up"
received_at: !relative_day {offset: -2, hour: 11, tz: America/New_York}
in_reply_to: !ref thread-darren-peter-exec-msg-darren-answer
labels: [inbox]
---
<p>Darren,</p>

<p>That is the answer I was hoping to hear. Maren — Amira will reach out this week to schedule a walkthrough. The per-partner agreement rate is exactly the number I want to see during the pilot.</p>

<p>We'll be ready to respond on the revised proposal Friday.</p>

<p>Peter</p>
