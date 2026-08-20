---
key: post-ship-decision-leo
model: PostComment
user: !ref leo
post: !ref post-ship-decision
created_at: !relative_day {offset: -2, hour: 10, tz: America/New_York}
updated_at: !relative_day {offset: -2, hour: 10, tz: America/New_York}
reactions:
  thumbs_up: [darren, emma]
---
For the record: I am comfortable with the scoped-both path if we are honest that the co-pilot v1 is a design-partner-only release behind a flag, not a GA feature, through Q3. That framing gets us both the coverage work Maren needs and the product signal I need.
