---
key: body
model: PostComment
user: !ref jordan
post: !ref post-eng-reading
created_at: !relative_day {offset: -6, hour: 13, tz: America/New_York}
updated_at: !relative_day {offset: -6, hour: 13, tz: America/New_York}
---
Kicking off an eng reading group on eval frameworks. First session is next Wednesday.

Reading list to start:
- The METR evaluation report methodology
- Anthropic's "Sleeper Agents" eval setup (relevant for the red-team work we're scoping)
- OpenAI's internal eval harness writeup

We'll meet for 45 minutes in the small room. Goal is to make our own eval harness less ad-hoc before the co-pilot ships.

If you want a specific paper covered, drop it in a reply.
