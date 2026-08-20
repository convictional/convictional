---
key: arjun-priya-dm-02-arjun-ack
model: EmailMessage
thread: !ref thread-arjun-priya-dm
user: !ref arjun
message_type: sent
sender: !ref arjun
to:
  - !ref priya
subject: "Re: Routing plan — two options"
received_at: !relative_day {offset: -1, hour: 11, tz: America/New_York}
---
<p>Priya,</p>

<p>Agreed on B. I already had the fallback concern — was going to propose a short-TTL in-process cache keyed by tenant ID. On startup we warm from DB; on a miss or error we fail open to the default region (us-east-1) and log a warning. Good enough for the edge case, won't route EU data to the wrong region because the EU tenant rows will be cached before any contract data flows.</p>

<p>I'll write up the ADR today. Want me to circulate before or after you and I sync?</p>

<p>Arjun</p>
