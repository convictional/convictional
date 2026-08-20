from collections.abc import Collection, Sequence
from dataclasses import dataclass
from uuid import UUID

import sentry_sdk

from app.models.collaboration.content import (
    Content,
    Research,
    iter_content_citations,
    scan_content_citations,
)
from app.models.commands import ResearchQuestion, ScheduledResearch
from config import logger, settings
from infra.email import EmailHeaders, EmailMessage, Mailer
from infra.llm import DEFAULT_MODEL


def _cited_content_ids(learnings: Collection[str]) -> set[UUID]:
    return {content_id for learning in learnings for content_id in iter_content_citations(learning)}


def record_dropped_citation_tokens(
    *,
    boundary: str,
    dropped_tokens: Sequence[str],
    total_citation_count: int,
    research_id: UUID,
    research_question_id: UUID | None = None,
) -> None:
    if not dropped_tokens:
        return

    if not settings.sentry_dsn:
        logger.debug("Research %s dropped %d unknown citation tokens", research_id, len(dropped_tokens))
        return

    with sentry_sdk.new_scope() as scope:
        scope.fingerprint = ["research-dropped-citation-tokens", boundary]
        scope.set_tag("research.citation_boundary", boundary)
        scope.set_tag("research.llm_model", DEFAULT_MODEL)
        scope.set_context(
            "Research Citations",
            {
                "research_id": str(research_id),
                "research_question_id": str(research_question_id) if research_question_id else None,
                "boundary": boundary,
                "dropped_token_count": len(dropped_tokens),
                "dropped_tokens": list(dropped_tokens),
                "total_citation_count": total_citation_count,
            },
        )
        sentry_sdk.capture_message("Research response dropped unknown citation tokens", level="warning")


async def record_unknown_content_citations(
    text: str | None,
    results_by_id: dict[UUID, Content],
    *,
    organization_id: UUID,
    research_id: UUID,
    learnings: Collection[str],
    research_question_id: UUID | None = None,
) -> None:
    unresolved, total_citation_count = scan_content_citations(text, results_by_id.keys())
    if not unresolved:
        return

    if not settings.sentry_dsn:
        # No Sentry off production — keep the signal discoverable locally rather than fully silent.
        logger.debug("Research %s cited %d unknown content ids", research_id, len(unresolved))
        return

    # Classify each unresolved id against the Content table using only queryable columns (id,
    # organization_id, content_type are not protected): no row means the model hallucinated the
    # id outright; a row owned by another org means it leaked a real id across the tenant boundary.
    rows = await Content.filter(id__in=unresolved).values("id", "organization_id", "content_type")
    row_by_id = {row["id"]: row for row in rows}

    hallucinated: list[UUID] = []
    foreign_same_org: list[UUID] = []
    cross_org: list[UUID] = []
    content_type_breakdown: dict[str, int] = {}
    for content_id in unresolved:
        row = row_by_id.get(content_id)
        if row is None:
            hallucinated.append(content_id)
            continue
        content_type = str(row["content_type"])
        content_type_breakdown[content_type] = content_type_breakdown.get(content_type, 0) + 1
        (foreign_same_org if row["organization_id"] == organization_id else cross_org).append(content_id)

    # Origin: an unresolved id already present in the learnings was introduced during extraction
    # (review_results prompt); one that surfaces only in the final report came from synthesis.
    learnings_cited = _cited_content_ids(learnings)
    from_extraction = [content_id for content_id in unresolved if content_id in learnings_cited]
    from_synthesis = [content_id for content_id in unresolved if content_id not in learnings_cited]
    if from_extraction and from_synthesis:
        citation_origin = "mixed"
    elif from_extraction:
        citation_origin = "extraction"
    else:
        citation_origin = "synthesis"

    if cross_org:
        unresolved_kind = "cross_org"
    elif foreign_same_org and hallucinated:
        unresolved_kind = "mixed"
    elif foreign_same_org:
        unresolved_kind = "foreign"
    else:
        unresolved_kind = "hallucinated"

    with sentry_sdk.new_scope() as scope:
        # Split issues by which LLM step to fix; the rest stay as tags so they can be faceted.
        scope.fingerprint = ["research-unknown-citations", citation_origin]
        scope.set_tag("research.citation_origin", citation_origin)
        scope.set_tag("research.unresolved_kind", unresolved_kind)
        scope.set_tag("research.has_cross_org", bool(cross_org))
        scope.set_tag("research.llm_model", DEFAULT_MODEL)
        scope.set_context(
            "Research Citations",
            {
                "organization_id": str(organization_id),
                "research_id": str(research_id),
                "research_question_id": str(research_question_id) if research_question_id else None,
                "unresolved_count": len(unresolved),
                "total_citation_count": total_citation_count,
                "unresolved_content_ids": [str(uuid) for uuid in unresolved],
                "hallucinated_count": len(hallucinated),
                "foreign_content_count": len(foreign_same_org),
                "cross_org_count": len(cross_org),
                "content_type_breakdown": content_type_breakdown,
                "citation_origin": citation_origin,
                "from_extraction_count": len(from_extraction),
                "from_synthesis_count": len(from_synthesis),
                "result_set_size": len(results_by_id),
                "llm_model": DEFAULT_MODEL,
            },
        )
        sentry_sdk.capture_message("Research response cited unknown content ids", level="warning")


@dataclass
class ResearchQuestionMailer(Mailer):
    research_question: ResearchQuestion

    async def send(self) -> str | None:
        message = await self.research_report_email()
        if not message:
            return None
        return await self.deliver(message)

    async def research_report_email(self) -> EmailMessage | None:
        if not self.research_question.research:
            return None

        headers = []

        if self.research_question.in_reply_to_message_id:
            headers.append({"name": "In-Reply-To", "value": self.research_question.in_reply_to_message_id})
            headers.append({"name": "References", "value": self.research_question.in_reply_to_message_id})

        cc = ", ".join(self.research_question.cc_recipients) if self.research_question.cc_recipients else ""
        message = EmailMessage(
            to=self.research_question.creator.email,
            cc=cc,
            send_from=settings.research_email_from,
            headers=EmailHeaders(headers),
        )

        results = await self._collect_all_results_by_id()
        await record_unknown_content_citations(
            self.research_question.response,
            results,
            organization_id=self.research_question.research.organization_id,
            research_id=self.research_question.research.id,
            learnings=self.research_question.research.learnings,
            research_question_id=self.research_question.id,
        )
        return self.render(
            message, "research_report.jinja", research_question=self.research_question, results_by_id=results
        )

    async def _collect_all_results_by_id(self) -> dict[UUID, Content]:
        if not self.research_question.research:
            return {}
        results = await self.research_question.research.fetch_results_by_id()

        thread_context = await self.research_question.get_thread_context(prefetch=["research__iterations__queries"])
        for prior_question in thread_context:
            if prior_question.research:
                prior_results = await prior_question.research.fetch_results_by_id()
                results.update(prior_results)

        return results


@dataclass
class ScheduledResearchMailer(Mailer):
    scheduled_research: ScheduledResearch
    research: Research
    rendered_markdown: str

    async def send(self) -> str | None:
        message = await self._build_message()
        return await self.deliver(message)

    async def _build_message(self) -> EmailMessage:
        results = await self.research.fetch_results_by_id()
        await record_unknown_content_citations(
            self.rendered_markdown,
            results,
            organization_id=self.research.organization_id,
            research_id=self.research.id,
            learnings=self.research.learnings,
        )
        message = EmailMessage(
            to=self.scheduled_research.creator.email,
            send_from=settings.research_email_from,
        )
        return self.render(
            message,
            "scheduled_research.jinja",
            scheduled_research=self.scheduled_research,
            rendered_markdown=self.rendered_markdown,
            results_by_id=results,
        )
