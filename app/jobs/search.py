import json
from dataclasses import asdict
from typing import Literal, cast
from uuid import UUID

from app.models.accounts import User
from app.models.collaboration.content import (
    Content,
    SearchDiagnostics,
    run_lookup_search,
    run_serp_search,
)
from config import logger
from config.enums import ContentType, JobQueue
from config.logging import LoggingContext
from infra.jobs import JobDefinition


class SearchDiagnosticJob(JobDefinition):
    """Run a user's search through the real production path and log why results came back the
    way they did. Built for the data-privacy blind spot: we can't see a user's corpus, so the
    report has to be self-contained — generated tsquery, a stage funnel, near-miss scores, and
    a per-expected-item verdict that names the stage where it dropped out.

    Run ad hoc from the superuser /background_jobs admin page; read the output from prod logs.
    """

    default_queue = JobQueue.MAINTENANCE
    retry_count = 0

    # Email rather than id so an operator can run this from the admin page without first
    # looking up a UUID in the prod DB (matches BulkGrantCollaboratorAccessJob et al.).
    user_email: str
    query: str
    search_type: Literal["serp", "lookup", "both"] = "both"
    content_type: ContentType | None = None
    # Expected-but-missing results to localize: each is a content id, a source_url, or a title
    # substring. Resolved ignoring access control so an access drop can itself be reported.
    expected: list[str] = []

    async def perform(self):
        user = await User.get_or_none(email=self.user_email).prefetch_related("organization")
        if not user:
            logger.warning(f"[search-diagnostic] user {self.user_email} not found")
            return

        with LoggingContext(
            user_id=str(user.id),
            organization_id=str(user.organization_id),
            search_query=self.query,
        ):
            expected_ids = await self._resolve_expected(user.organization_id)
            logger.info(
                f"[search-diagnostic] user={user.email} org={user.organization_id} "
                f"content_type={self.content_type.value if self.content_type else 'all'} "
                f"access_mode=organization+private expected_resolved={len(expected_ids)}"
            )

            if self.search_type in ("serp", "both"):
                await self._diagnose_serp(user, expected_ids)
            if self.search_type in ("lookup", "both"):
                await self._diagnose_lookup(user, expected_ids)

    async def _diagnose_serp(self, user: User, expected_ids: list[UUID]) -> None:
        results, search = await run_serp_search(
            organization=user.organization,
            query=self.query,
            user=user,
            content_type=self.content_type,
            collect_diagnostics=True,
        )
        result_ids = [r.id for r in results]
        ranked = [
            {
                "content_id": str(content.id),
                "content_type": content.content_type.value,
                **search.component_scores.get(content.id, {}),
            }
            for content in results
        ]
        near_misses = [{**miss, "content_id": str(miss["content_id"])} for miss in await search.near_misses()]
        diagnostics = SearchDiagnostics(
            query=self.query,
            normalized_query=search.normalized_query(),
            tsquery=await search.generated_tsquery(),
            funnel=await search.funnel(),
            result_count=len(results),
            results=ranked,
            near_misses=near_misses,
            targets=[await search.diagnose_target(content_id, result_ids) for content_id in expected_ids],
        )
        self._log_report("serp", diagnostics)

    async def _diagnose_lookup(self, user: User, expected_ids: list[UUID]) -> None:
        results, lookup = await run_lookup_search(
            organization=user.organization,
            query=self.query,
            user=user,
            collect_diagnostics=True,
        )
        result_ids = [r.id for r in results]
        ranked = [
            {
                "content_id": str(content.id),
                "content_type": content.content_type.value,
                "score": lookup.result_scores.get(content.id),
            }
            for content in results
        ]
        diagnostics = SearchDiagnostics(
            query=self.query,
            normalized_query=lookup.normalized_query(),
            tsquery=await lookup.generated_tsquery(),
            funnel=await lookup.funnel(),
            result_count=len(results),
            results=ranked,
            near_misses=[],
            targets=[await lookup.diagnose_target(content_id, result_ids) for content_id in expected_ids],
            fallback_used=lookup.used_trigram_fallback,
        )
        self._log_report("lookup", diagnostics)

    async def _resolve_expected(self, organization_id: UUID) -> list[UUID]:
        resolved: list[UUID] = []
        for matcher in self.expected:
            ids = await self._resolve_matcher(organization_id, matcher)
            if ids:
                resolved.extend(ids)
            else:
                logger.warning(f"[search-diagnostic] expected matcher resolved to no content: {matcher!r}")

        return list(dict.fromkeys(resolved))

    @staticmethod
    async def _resolve_matcher(organization_id: UUID, matcher: str) -> list[UUID]:
        try:
            return [UUID(matcher)]
        except ValueError:
            pass

        if matcher.startswith("http"):
            query = Content.filter(organization_id=organization_id, source_url=matcher)
        else:
            query = Content.filter(organization_id=organization_id, title__icontains=matcher).limit(10)
        return cast(list[UUID], list(await query.values_list("id", flat=True)))

    @staticmethod
    def _log_report(label: str, diagnostics: SearchDiagnostics) -> None:
        lines = [
            f"[search-diagnostic:{label}] query={diagnostics.query!r} normalized={diagnostics.normalized_query!r}",
            f"  tsquery: {diagnostics.tsquery!r}",
            f"  fallback: {diagnostics.fallback_used}",
            f"  funnel: {diagnostics.funnel}",
            f"  results ({diagnostics.result_count}):",
        ]
        for rank, result in enumerate(diagnostics.results):
            score = result.get("relevance_score", result.get("score"))
            lines.append(f"    {rank}. {result['content_type']} {result['content_id']} score={score}")
        if diagnostics.near_misses:
            lines.append("  near misses (scored below the relevance floor):")
            for miss in diagnostics.near_misses:
                lines.append(f"    - {miss['content_type']} {miss['content_id']} score={miss['relevance_score']}")
        if diagnostics.targets:
            lines.append("  expected items:")
            for target in diagnostics.targets:
                lines.append(f"    - {target.content_id}: {target.verdict}")

        payload = json.loads(json.dumps({"search_diagnostic": asdict(diagnostics)}, default=str))
        logger.info("\n".join(lines), extra={"json_fields": payload})
