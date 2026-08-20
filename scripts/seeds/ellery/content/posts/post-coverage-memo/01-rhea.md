---
key: post-coverage-memo-rhea
model: PostComment
user: !ref rhea
post: !ref post-coverage-memo
created_at: !relative_day {offset: -7, hour: 10, tz: America/New_York}
updated_at: !relative_day {offset: -7, hour: 10, tz: America/New_York}
reactions:
  thumbs_up: [maren, jordan]
  eyes: [leo]
---
The numbers, from the coverage gap analysis I've been running:

- **DPAs:** ~38% playbook coverage against the clause set our 5 largest customers actually see. This is the one.
- **MSAs (generic):** ~71%. Fine.
- **Industry MSAs (SaaS, healthcare, fintech):** 44%. Also the one.
- **NDAs:** 86%. Move along.

DPAs and industry MSAs are where a customer will send us a paragraph we cannot confidently opine on. The co-pilot will amplify this — if we can't get the clause right manually, the AI version will be wrong at the speed of light.
