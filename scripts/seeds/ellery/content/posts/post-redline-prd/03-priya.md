---
key: post-redline-prd-priya
model: PostComment
user: !ref priya
post: !ref post-redline-prd
created_at: !relative_day {offset: -12, hour: 11, tz: America/New_York}
updated_at: !relative_day {offset: -12, hour: 11, tz: America/New_York}
reactions:
  thumbs_up: [leo, jordan]
---
Clarifying question on the retrieval architecture: are we planning to serve the customer's playbook + their prior edits from a single index, or do we route differently for the two sources? The PRD reads as if it is one index. That matters for latency and for how we handle playbook updates mid-review.

Not a blocker. But the answer shapes how much infra work the rest of the proposal implies.
