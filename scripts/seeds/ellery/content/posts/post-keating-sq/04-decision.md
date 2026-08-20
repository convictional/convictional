---
key: post-keating-sq-decision
model: PostComment
user: !ref priya
post: !ref post-keating-sq
is_decision_comment: true
created_at: !relative_day {offset: -11, hour: 16, minute: 20, tz: America/New_York}
updated_at: !relative_day {offset: -11, hour: 16, minute: 20, tz: America/New_York}
reactions:
  thumbs_up: [arjun, theo, maren]
  rocket: [darren]
---
Locking the split:

- **Q1-Q38 (Security architecture)** — Arjun owns. Include the residency ADR as a reference document once it's final.
- **Q39-Q72 (Data handling & privacy)** — Maren owns. Flag the ~20 items downstream of the residency decision as "conditional on ADR landing" rather than blocking.
- **Q73-Q147 (Model controls, evals, abuse)** — Jordan owns.

Return deadline: one week from today. Single review pass by me before it goes to Doug. If any answer surfaces a real commitment we can't meet, flag it up immediately — better to negotiate wording than to overpromise.
