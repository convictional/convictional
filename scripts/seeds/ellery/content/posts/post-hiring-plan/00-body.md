---
key: body
model: PostComment
user: !ref priya
post: !ref post-hiring-plan
created_at: !relative_day {offset: -10, hour: 9, tz: America/New_York}
updated_at: !relative_day {offset: -10, hour: 9, tz: America/New_York}
---
Here is my proposed order for the first three engineering hires: **SRE, second ML engineer, integrations engineer**.

The thinking: SOC 2 and Keating's uptime expectations mean we cannot keep paging Arjun every time a region flaps. SRE first. Second ML unblocks Jordan on the eval harness and the co-pilot prototype. Integrations engineer comes third because the legal-ops pattern is real but the pipeline is still small.

I'd rather hire one great SRE in eight weeks than two decent backend generalists in four. Pushback welcome.

https://lethain.com/eng-strategies/
