---
key: post-redline-prd-jordan
model: PostComment
user: !ref jordan
post: !ref post-redline-prd
created_at: !relative_day {offset: -13, hour: 14, tz: America/New_York}
updated_at: !relative_day {offset: -13, hour: 14, tz: America/New_York}
reactions:
  thumbs_up: [priya, maren]
  eyes: [leo]
---
Love the ambition. Honest flag on eval timeline: the prototype works in a demo because the happy path is narrow. The failure modes we see in ground-truth data — wrong clause identified, overconfident paraphrase, missed governing-law swap — will not be caught by the current evals.

I need at least four weeks with Rhea to stand up a defensible harness before we ship this behind a flag to real customers. Shipping it to design partners sooner means accepting that we will eat some credibility hits.
