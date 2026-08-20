---
key: body
model: PostComment
user: !ref maren
post: !ref post-coverage-memo
created_at: !relative_day {offset: -7, hour: 8, tz: America/New_York}
updated_at: !relative_day {offset: -7, hour: 8, tz: America/New_York}
---
Counter-memo to Leo's PRD.

I agree with most of what Leo wrote. Where we differ is sequencing. Before we ship an AI assistant that recommends redlines, we owe our existing customers (and Keating, and every pilot after) *defensible playbook coverage on the contract types they actually send us.*

Right now: DPA coverage is thin, industry-specific MSA coverage is a known gap, and NDA coverage is good-enough-but-not-embarrassing. Alderman asked last week for DPA work they assumed we already had. Rhea has the numbers.

We should close the floor before we build the ceiling. Full memo linked in the doc index.
