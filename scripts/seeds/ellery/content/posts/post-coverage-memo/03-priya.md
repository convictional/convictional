---
key: post-coverage-memo-priya
model: PostComment
user: !ref priya
post: !ref post-coverage-memo
created_at: !relative_day {offset: -7, hour: 15, tz: America/New_York}
updated_at: !relative_day {offset: -7, hour: 15, tz: America/New_York}
reactions:
  thumbs_up: [maren, leo, darren]
---
Neutral engineering framing, no opinion on which is the right bet:

- **Coverage-only path:** Rhea + a second content analyst can close DPA and industry-MSA gaps in ~8 weeks. Zero engineering load beyond reindexing.
- **Co-pilot-only path:** Jordan + me + Theo's UI work = ~10 weeks to a defensible behind-a-flag release. Assumes we don't also run the SOC 2 and residency workstreams with zero headroom, which we are.
- **Both-in-parallel:** possible, but requires the SRE hire to land on time and the 2nd content analyst req to open this week, and the co-pilot ships slower than Leo's PRD assumes.

Numbers are on the engineering-chat thread.
