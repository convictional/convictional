---
key: post-ship-decision-decision
model: PostComment
user: !ref darren
post: !ref post-ship-decision
is_decision_comment: true
created_at: !relative_day {offset: -1, hour: 10, minute: 15, tz: America/New_York}
updated_at: !relative_day {offset: -1, hour: 10, minute: 15, tz: America/New_York}
reactions:
  rocket: [leo, jordan]
  heart: [maren]
  thumbs_up: [priya, emma, rhea]
---
Closing this with a scoped-both approach. The decision:

1. **Coverage is the GA gate for the redline co-pilot.** Maren's counter-memo and Emma's research synthesis converge on the same point — lawyers do not trust the tool once it's been confidently wrong. We will not GA on the co-pilot until commercial-contract playbook coverage is ≥ 90% on MSA, NDA, SOW, and DPA.

2. **Flag-first deployment to the three current design-partner customers continues.** The private-beta cohort runs in parallel with coverage work. Research sessions continue through the pilot.

3. **No external announcement of co-pilot until (1) is met.** Tessa, update the sales narrative to reflect "approaching GA behind trust gates" rather than a target date.

Leo owns the integrated roadmap. Maren owns the coverage-metric definition. Priya and Jordan own the eval framework updates that will tell us when we've hit the gate.
