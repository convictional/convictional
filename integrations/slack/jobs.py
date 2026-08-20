from dataclasses import dataclass

from app.jobs.research import MAX_NUMBER_OF_SEARCH_RESULTS, ResearchSearch
from app.models.accounts import User
from app.models.collaboration.content import BaseSearch, ResearchQuery
from config import logger
from config.enums import ContentCategory, ContentType, Integration
from integrations.slack.client import SlackClient
from integrations.slack.models import ExpandedMessageContext, SlackContent, SlackMessage


@dataclass
class ResearchSlackSearch(ResearchSearch):
    async def perform(self):
        self.research_query = await ResearchQuery.create(
            iteration_id=self.iteration.id,
            research_id=self.iteration.research_id,
            research=self.iteration.research,
            title=self.generated_query.title,
            starts_at=self.generated_query.starts_at,
            ends_at=self.generated_query.ends_at,
            goals=self.generated_query.goals,
            source=self.generated_query.source,
        )

        search = SlackSearch(
            organization=self.iteration.research.creator.organization,
            query=self.generated_query.terms,
            user=self.iteration.research.creator,
            starts_at=self.research_query.starts_at,
            ends_at=self.research_query.ends_at,
            limit=MAX_NUMBER_OF_SEARCH_RESULTS,
        )

        self.results = await search.execute()
        await self.research_query.save_content_search(search, self.results)


def is_slack_configured(user: User) -> bool:
    return user.is_integrated_with(Integration.SLACK)


FIFTEEN_MINUTES_IN_SECONDS = 15 * 60
EXPANSION_TIME_WINDOW = FIFTEEN_MINUTES_IN_SECONDS
MAX_SURROUNDING_MESSAGES = 10
MAX_THREAD_MESSAGES = 20


@dataclass
class SlackSearch(BaseSearch):
    async def execute(self) -> list[SlackContent]:
        if not self.user:
            logger.warning("SlackSearch executed without a user; returning no results.")
            return []

        client = await SlackClient.create(self.user)
        search_results = await client.search_messages(
            query=self.query,
            limit=self.limit,
            starts_at=self.starts_at,
            ends_at=self.ends_at,
        )

        if not search_results:
            return []

        expanded_contexts = await self.expand_message_context(client, search_results)

        results = []
        for result in search_results:
            context = expanded_contexts.get(result.message_id)
            if context:
                index_content = context.to_text()
            else:
                index_content = result.text

            title = f"Slack Message from {result.username} in #{result.channel_name} ({result.datetime})"

            slack_content = await SlackContent.create(
                organization=self.organization,
                source_id=result.message_id,
                source_url=result.permalink,
                content_type=ContentType.SLACK_MESSAGE,
                category=ContentCategory.ACTIVITY,
                title=title,
                title_normalized=title.lower(),
                index_content=index_content,
                author=result.username,
            )
            results.append(slack_content)

        return results

    async def expand_message_context(
        self,
        client: SlackClient,
        messages: list[SlackMessage],
    ) -> dict[str, ExpandedMessageContext]:
        expanded: dict[str, ExpandedMessageContext] = {}

        for message in messages:
            parent_thread_ts = message.thread_ts
            is_thread_reply = parent_thread_ts is not None and parent_thread_ts != message.timestamp

            if is_thread_reply and parent_thread_ts:
                full_thread = await client.get_thread_replies(
                    channel_id=message.channel_id,
                    thread_ts=parent_thread_ts,
                    limit=MAX_THREAD_MESSAGES,
                    include_parent=True,
                )
                expanded[message.message_id] = ExpandedMessageContext(
                    matched_message=message,
                    is_thread_reply=True,
                    full_thread=full_thread,
                )
            else:
                message_ts = float(message.timestamp)
                oldest_ts = str(message_ts - EXPANSION_TIME_WINDOW)
                latest_ts = str(message_ts + EXPANSION_TIME_WINDOW)

                surrounding = await client.get_conversation_history(
                    channel_id=message.channel_id,
                    oldest=oldest_ts,
                    latest=latest_ts,
                    limit=MAX_SURROUNDING_MESSAGES + 1,
                )
                prior = [m for m in surrounding if float(m.timestamp) < message_ts]
                subsequent = [m for m in surrounding if float(m.timestamp) > message_ts]

                thread_replies: list[SlackMessage] = []

                thread_replies = await client.get_thread_replies(
                    channel_id=message.channel_id,
                    thread_ts=message.timestamp,
                    limit=MAX_THREAD_MESSAGES,
                )

                expanded[message.message_id] = ExpandedMessageContext(
                    matched_message=message,
                    prior_messages=sorted(prior, key=lambda m: m.timestamp),
                    subsequent_messages=sorted(subsequent, key=lambda m: m.timestamp),
                    thread_replies=thread_replies,
                )

        return expanded
