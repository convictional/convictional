from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.models.collaboration.content import Content
from app.models.workspaces.goals import GoalAlignment
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post
from config.enums import ContentCategory, ContentType, Sharing, SignalStrength
from infra.db import GlobalID
from scripts.seeds.ellery.accounts import People
from scripts.seeds.seeder import Ref, create

# GoalAlignment rows are produced in production by the weekly ScoreGoalAlignmentJob (an LLM scores
# each org Post/Meeting against every active goal). Seeding runs before content is indexed, so we
# also materialize the Content rows the alignments point at, keyed by each source's GlobalID. The
# post-seed IndexSearchJob reconciles those same rows in place via Content's (organization_id,
# source_id) unique key, enriching them with embeddings without creating duplicates.


@dataclass(frozen=True)
class AlignmentSpec:
    source: str  # seed key of the Post/Meeting the content mirrors
    kind: str  # "Post" or "Meeting"
    signal: SignalStrength
    score: float
    days_ago: int  # content_indexed_at, relative to now — must fall inside the goal's activation window
    description: str
    pinned: bool = False  # goal owner pinned a job suggestion (created_by stays null)
    manual: bool = False  # goal owner manually added it (created_by + pinned_by set, score forced to 1.0)


@dataclass(frozen=True)
class GoalAlignments:
    goal: str  # seed key of the top-level goal
    owner: str  # seed key of the goal owner (the user who pins / manually aligns)
    specs: list[AlignmentSpec] = field(default_factory=list)


S = SignalStrength

# Each goal below is a real active, open, top-level Ellery goal; every source is a seeded Post or
# Meeting whose theme genuinely supports the goal. Signal/score tiers: strong ~0.83–0.94,
# medium ~0.64–0.78, weak ~0.55–0.62 (all >= the 0.5 the scorer requires to persist).
PLAN: list[GoalAlignments] = [
    GoalAlignments(
        goal="chief",
        owner="darren",
        specs=[
            AlignmentSpec(
                "post-why-cos",
                "Post",
                S.STRONG,
                0.94,
                15,
                "Darren's announcement lays out the rationale and scope for the Chief of Staff hire, "
                "framing the goal's intent directly.",
                pinned=True,
            ),
            AlignmentSpec(
                "post-cos-finalists",
                "Post",
                S.STRONG,
                0.90,
                6,
                "The finalist panel roundup summarizes the CoS candidates and the team's read on each, "
                "tracking direct progress toward the hire.",
                pinned=True,
            ),
            AlignmentSpec(
                "mtg-cos-final-priyanka",
                "Meeting",
                S.STRONG,
                0.88,
                4,
                "A final-round call with CoS candidate Priyanka Deol — a late-stage step in the interview loop.",
            ),
            AlignmentSpec(
                "mtg-cos-onsite-priyanka",
                "Meeting",
                S.STRONG,
                0.85,
                9,
                "An on-site interview with CoS finalist Priyanka Deol, advancing her through the hiring loop.",
            ),
            AlignmentSpec(
                "mtg-cos-onsite-naomi",
                "Meeting",
                S.STRONG,
                0.84,
                12,
                "An on-site interview with CoS finalist Naomi Fisk, part of the finalist evaluation for the role.",
            ),
            AlignmentSpec(
                "mtg-cos-scorecard-workshop",
                "Meeting",
                S.MEDIUM,
                0.72,
                14,
                "The scorecard workshop defines the rubric the team uses to evaluate Chief of Staff candidates.",
            ),
            AlignmentSpec(
                "post-recruiter-debrief",
                "Post",
                S.MEDIUM,
                0.66,
                3,
                "The Halverson Partners recruiter debrief covers the executive search feeding the CoS shortlist.",
            ),
        ],
    ),
    GoalAlignments(
        goal="hire",
        owner="darren",
        specs=[
            AlignmentSpec(
                "post-hiring-order",
                "Post",
                S.STRONG,
                0.91,
                19,
                "This post drives the exec decision on hiring sequence — the core planning artifact for "
                "staffing the Series A roles.",
                pinned=True,
            ),
            AlignmentSpec(
                "post-hiring-plan",
                "Post",
                S.STRONG,
                0.88,
                16,
                "The v1 engineering hiring plan details the roles, levels, and timing for the technical "
                "portion of the hiring goal.",
            ),
            AlignmentSpec(
                "mtg-engineering-hiring-deepdive",
                "Meeting",
                S.STRONG,
                0.85,
                11,
                "A deep-dive on engineering hiring needs and role prioritization that feeds the staffing plan.",
            ),
            AlignmentSpec(
                "post-ic-profiles",
                "Post",
                S.MEDIUM,
                0.74,
                7,
                "Defining what 'good' looks like for senior ICs sets the bar for the engineering roles being hired.",
            ),
            AlignmentSpec(
                "post-recruiter-debrief",
                "Post",
                S.WEAK,
                0.58,
                4,
                "The Halverson Partners recruiter debrief touches on executive sourcing relevant to the broader "
                "hiring push.",
            ),
        ],
    ),
    GoalAlignments(
        goal="keating",
        owner="tessa",
        specs=[
            AlignmentSpec(
                "post-keating-health",
                "Post",
                S.STRONG,
                0.93,
                20,
                "Tessa's deal-health post tracks Keating & Marsh status, open asks, and risks — the running "
                "pulse on this goal.",
                pinned=True,
            ),
            AlignmentSpec(
                "mtg-keating-deal-review",
                "Meeting",
                S.STRONG,
                0.90,
                17,
                "The deal review walks the Keating & Marsh opportunity end to end, the central working session "
                "for closing it.",
            ),
            AlignmentSpec(
                "mtg-keating-exec-demo",
                "Meeting",
                S.STRONG,
                0.86,
                13,
                "The exec demo to Keating & Marsh is a pivotal sales milestone in landing the account.",
            ),
            AlignmentSpec(
                "post-keating-exec-demo",
                "Post",
                S.STRONG,
                0.87,
                9,
                "Lessons from the Keating exec demo capture what moved the buying committee and what to fix "
                "before close.",
            ),
            AlignmentSpec(
                "post-keating-sq",
                "Post",
                S.MEDIUM,
                0.75,
                5,
                "Splitting the security questionnaire unblocks the procurement step required to close "
                "Keating & Marsh.",
            ),
            AlignmentSpec(
                "mtg-soc2-readiness-review",
                "Meeting",
                S.MEDIUM,
                0.66,
                2,
                "SOC 2 readiness addresses the enterprise security bar Keating's vendor review requires.",
            ),
            AlignmentSpec(
                "mtg-residency-adr-review",
                "Meeting",
                S.WEAK,
                0.57,
                15,
                "The EU data-residency decision bears on enterprise requirements that surface in deals like Keating.",
            ),
        ],
    ),
    GoalAlignments(
        goal="rhythm",
        owner="maren",
        specs=[
            AlignmentSpec(
                "post-operating-rhythm",
                "Post",
                S.STRONG,
                1.0,
                13,
                "Maren's operating-rhythm draft is the primary proposal defining the post-raise cadence this "
                "goal targets.",
                manual=True,
            ),
            AlignmentSpec(
                "post-okrs-draft",
                "Post",
                S.STRONG,
                0.86,
                10,
                "The first company OKRs draft establishes the goal-setting layer of the new operating rhythm.",
            ),
            AlignmentSpec(
                "post-series-a",
                "Post",
                S.MEDIUM,
                0.70,
                6,
                "The Series A kickoff post sets expectations for how the company operates in the new stage.",
            ),
            AlignmentSpec(
                "post-thanks-round",
                "Post",
                S.WEAK,
                0.55,
                3,
                "A note of thanks to the round touches on the post-raise transition the operating rhythm formalizes.",
            ),
        ],
    ),
    GoalAlignments(
        goal="ship",
        owner="leo",
        specs=[
            AlignmentSpec(
                "post-ship-decision",
                "Post",
                S.STRONG,
                0.94,
                13,
                "The Ship post is the decision thread for locking the Q3 roadmap — this goal's central artifact.",
                pinned=True,
            ),
            AlignmentSpec(
                "post-coverage-memo",
                "Post",
                S.STRONG,
                0.88,
                11,
                "Maren's coverage-first counter-memo is a key position in the roadmap debate this goal "
                "aims to resolve.",
            ),
            AlignmentSpec(
                "post-redline-prd",
                "Post",
                S.STRONG,
                0.86,
                8,
                "The Redline Co-pilot PRD specifies one of the Q3 product bets under debate.",
            ),
            AlignmentSpec(
                "mtg-redline-copilot-design-review",
                "Meeting",
                S.STRONG,
                0.83,
                5,
                "The design review advances the Redline Co-pilot bet toward a locked Q3 commitment.",
            ),
            AlignmentSpec(
                "post-product-principles",
                "Post",
                S.MEDIUM,
                0.72,
                3,
                "The v0 product principles frame the criteria the team uses to choose among Q3 bets.",
            ),
            AlignmentSpec(
                "post-research-plan",
                "Post",
                S.MEDIUM,
                0.64,
                1,
                "The redline co-pilot research plan gathers the customer evidence informing the roadmap decision.",
            ),
            AlignmentSpec(
                "post-brownbag-calls",
                "Post",
                S.WEAK,
                0.56,
                12,
                "Customer-call learnings from the brownbag feed the demand signal behind the roadmap choices.",
            ),
        ],
    ),
]

_CONTENT_META = {
    "Post": (ContentCategory.DOCUMENT, ContentType.POST),
    "Meeting": (ContentCategory.ACTIVITY, ContentType.MEETING),
}


async def _content_for(source: str, kind: str) -> Content:
    """Get-or-create the Content row a source's alignments point at, mirroring the indexer's output.

    Keyed by the source's GlobalID so the post-seed IndexSearchJob reconciles the same row.
    """
    ref = Ref(source)
    source_gid = str(GlobalID.create(kind, ref.id))
    category, content_type = _CONTENT_META[kind]

    if kind == "Post":
        post = await Post.get(id=ref.id).select_related("creator")
        title = post.title
        author = post.creator.display_name
    else:
        meeting = await Meeting.get(id=ref.id)
        title = meeting.title
        author = ", ".join(a.display_name for a in meeting.attendees if a.display_name)

    return await create(
        Content,
        f"align-content-{source}",
        category=category,
        content_type=content_type,
        source_id=source_gid,
        source_url=source_gid,
        title=title,
        author=author,
        # Real index_content/preview_content are backfilled by IndexSearchJob; title keeps the
        # not-null column valid and readable in dry runs before indexing.
        index_content=title,
        sharing=Sharing.ORGANIZATION,
    )


async def seed_alignments(people: People) -> None:
    now = datetime.now(UTC)

    for plan in PLAN:
        for spec in plan.specs:
            content = await _content_for(spec.source, spec.kind)

            kwargs = {
                "goal": Ref(plan.goal),
                "content": content,
                "content_indexed_at": now - timedelta(days=spec.days_ago),
                "signal": spec.signal,
                "alignment_score": spec.score,
                "description": spec.description,
            }
            if spec.manual:
                kwargs["created_by"] = Ref(plan.owner)
                kwargs["pinned_by"] = Ref(plan.owner)
            elif spec.pinned:
                kwargs["pinned_by"] = Ref(plan.owner)

            await create(GoalAlignment, f"align-{plan.goal}-{spec.source}", **kwargs)
