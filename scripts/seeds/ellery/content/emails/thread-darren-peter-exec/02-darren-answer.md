---
key: msg-darren-answer
model: EmailMessage
thread: !ref thread-darren-peter-exec
user: !ref darren
message_type: sent
sender: !ref darren
to:
  - "Peter Nakagawa <peter.nakagawa@keatingmarsh.com>"
cc:
  - !ref tessa
  - !ref maren
subject: "Re: Post-demo follow-up"
sent_at: !relative_day {offset: -3, hour: 14, tz: America/New_York}
in_reply_to: !ref thread-darren-peter-exec-msg-peter-thanks
---
<p>Peter,</p>

<p>Thank you — and I'll answer directly.</p>

<p>Our system blends two signals: the playbook you configure (the rules you'd give a first-year associate) and your own edit history as the system sees it. The playbook is the floor. The edit history — who redlined what, in what direction, under which counterparty conditions — is the texture. Over the first 60 days in a real firm's environment, the edit history dominates. We measure this explicitly: one of our evals is "would this redline match the partner's own prior edit pattern on this clause type?" We want that number high. We actively do not want homogenized output, and we monitor for exactly that.</p>

<p>Two concrete commitments I'm comfortable making:</p>
<ul>
<li>During the pilot we will show you per-partner, per-clause-type agreement rates so you can see whether the system is learning "you" or averaging "everyone."</li>
<li>Your redline history and playbook are yours. We do not train shared models on your data. Your texture is not shared across customers. Maren has written the contract language and is happy to walk Amira through it.</li>
</ul>

<p>Our Head of Legal Product, Maren Kovacs, spent a decade practicing and is the right person to go deeper on "how your firm's way of doing things shows up in the system." I've copied her — she'll follow up on a time with you.</p>

<p>Thank you for asking the real question.</p>

<p>Darren Okafor<br>
<em>CEO, Ellery</em></p>
