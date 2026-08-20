---
key: post-hiring-plan-arjun
model: PostComment
user: !ref arjun
post: !ref post-hiring-plan
created_at: !relative_day {offset: -10, hour: 11, tz: America/New_York}
updated_at: !relative_day {offset: -10, hour: 11, tz: America/New_York}
reactions:
  thumbs_up: [priya, darren]
  heart: [theo]
---
Strong yes on SRE first. I have been doing the SRE work on the side for six months and it is going to break if Keating signs and we onboard them in parallel with EU residency.

One thing worth naming: the SRE we want is someone who has run production for a data-sensitive B2B company before, not a platform SRE from a consumer shop. The failure mode for the cheaper hire is someone who optimizes for scale we don't need while the legal-hold flow keeps timing out.
