---
key: post-keating-health-arjun
model: PostComment
user: !ref arjun
post: !ref post-keating-health
created_at: !relative_day {offset: -3, hour: 14, tz: America/New_York}
updated_at: !relative_day {offset: -3, hour: 14, tz: America/New_York}
reactions:
  heart: [tessa, priya]
  thumbs_up: [darren]
---
Q44 response draft is in the deal doc. Short version: we terminate customer data at the region boundary, KMS keys are region-scoped and rotated on our schedule, and we support customer-managed keys on the Keating tier. Doug should be happy; if he is not, I want 20 minutes with him and a whiteboard.
