---
key: update-engineering-1
model: GoalUpdate
goal: !ref hire-goal-engineering
creator: !ref priya
status: on_track
progress: 0.10
created_at: !relative_day {offset: -14, hour: 11, tz: America/New_York}
---
Published the engineering hiring plan memo. Reasoning for SRE-first: we do not have a single on-call rotation that can credibly answer the Keating CISO's questions about uptime, and the 2nd ML engineer is dead weight until we have the infra to run evals at scale.
