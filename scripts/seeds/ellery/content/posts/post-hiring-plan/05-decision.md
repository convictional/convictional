---
key: post-hiring-plan-decision
model: PostComment
user: !ref priya
post: !ref post-hiring-plan
is_decision_comment: true
created_at: !relative_day {offset: -9, hour: 10, tz: America/New_York}
updated_at: !relative_day {offset: -9, hour: 10, tz: America/New_York}
reactions:
  rocket: [darren, arjun]
  heart: [jordan]
  thumbs_up: [theo, tessa]
---
Thanks everyone. Locking this in as our engineering hiring order: **SRE → 2nd ML (evals/retrieval specialist) → integrations engineer (legal-ops-facing)**.

To Darren's question — integrations is scoped legal-ops-first. Mateo, I'll send you a profile by Friday.

To Jordan's point — agreed, we are hiring an evals specialist, not a generalist. I'll adjust the scorecard language before we publish the req.

Tessa — totally fair. Darren is opening a separate exec-level post on Q3 cross-functional ordering so GTM gets its real hearing there.
