---
key: arjun-priya-dm-01-priya-routing
model: EmailMessage
thread: !ref thread-arjun-priya-dm
user: !ref arjun
message_type: received
sender: !ref priya
to:
  - !ref arjun
subject: "Re: Routing plan — two options"
received_at: !relative_day {offset: -1, hour: 10, tz: America/New_York}
---
<p>Arjun,</p>

<p>I looked at both options you sketched. Quick take:</p>

<p><strong>Option A (geo-based routing at the API gateway layer):</strong> Simpler, easier to audit, but it means every request pays the latency of a region lookup even for US customers. With Keating's use case — their associates are doing live redlines — that might be noticeable at tail latency.</p>

<p><strong>Option B (tenant-scoped routing table in the application layer):</strong> More work upfront, but it's the right long-term shape. Once we have more than two regions, doing this at the app layer means the gateway stays dumb. I'd go this way.</p>

<p>The one concern I have with B: the routing table becomes a single point of failure if the DB goes down. Do you have a fallback plan? Cache the routing decision per tenant at request startup so a brief DB blip doesn't black-hole EU traffic?</p>

<p>Let's sync on this before the Brandt call Thursday — I want the architecture locked before we're describing it to an auditor.</p>

<p>Priya</p>
