---
key: msg-emma-prompts-reply
model: EmailMessage
thread: !ref thread-leo-emma-dm
user: !ref leo
message_type: received
sender: !ref emma
to:
  - !ref leo
subject: "Re: Research prompts — v2"
received_at: !relative_day {offset: -5, hour: 23, tz: America/New_York}
in_reply_to: !ref thread-leo-emma-dm-msg-leo-research-prompts
labels: [inbox]
---
<p>Leo,</p>

<p>Points 1 and 2 are great additions — pulling those in.</p>

<p>Reframing point 3: I'll end sessions with "walk me through the last time you trusted a software suggestion and the last time you didn't. What was different?" That gives us the trust signal you're looking for without leading toward a yes. The behavioral data will be more useful than the hypothetical one anyway.</p>

<p>Also: session 3 this afternoon with a junior associate at Alderman was surprising. More on this tomorrow when I've written it up properly. Short version: she's using the tool in a way we didn't design for, and it might be more interesting than what we built.</p>

<p>Emma</p>
