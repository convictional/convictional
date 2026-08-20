import re
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, ClassVar
from uuid import UUID

import asyncpg
import tortoise.exceptions
from pydantic import BaseModel
from tortoise import BaseDBAsyncClient, Tortoise, fields
from tortoise.expressions import Q

from app.models.accounts import Organization, User
from app.models.collaboration.mixins import TaggableMixin
from config import logger, settings
from config.enums import ContentCategory, ContentType, ResearchSource, Sharing
from infra.db import GinIndex, GlobalID, HnswIndex, JSONField, PrefixIndex, RecordModel, TSVectorField, VectorField
from infra.jobs import Job
from infra.vectors import EMBEDDING_DIMENSION
from lib.encoding import EMBEDDING_ENCODING, chunk_string
from lib.strings import normalize_text

#
# Content
#
#

content_model_registry: list[type["Content"]] = []

EMBEDDING_TOKENS = 8100
RESULTS_PER_TYPE_LIMIT = 10
INDEX_CONTENT_MAX_LENGTH = 500_000
INDEX_CONTENT_FALLBACK_MAX_LENGTH = 100_000

CONTENT_CITATION_PATTERN = r"\[\^content:(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]"
RESEARCH_TOKEN_PATTERN = r"\[\^S(?P<n>\d+)\]"


def iter_content_citations(text: str | None) -> Iterator[UUID]:
    """Yield the content id of every `[^content:<uuid>]` citation marker, in order and with
    repeats — the shared primitive for reading citation markers out of a string."""
    if not text:
        return
    for match in re.finditer(CONTENT_CITATION_PATTERN, text):
        yield UUID(match.group("uuid"))


def scan_content_citations(text: str | None, known_ids: Collection[UUID]) -> tuple[list[UUID], int]:
    """Single pass over a report's citation markers.

    Returns (unresolved_ids, total_citation_count), where unresolved ids are those not in
    known_ids, de-duplicated in first-appearance order, and the total counts every marker.
    """
    known = set(known_ids)
    unresolved: list[UUID] = []
    seen: set[UUID] = set()
    total = 0
    for content_id in iter_content_citations(text):
        total += 1
        if content_id in known or content_id in seen:
            continue
        seen.add(content_id)
        unresolved.append(content_id)

    return unresolved, total


@dataclass(frozen=True)
class DetokenizeResult:
    """Outcome of detokenizing a batch of texts: the rewritten texts, the de-duplicated
    unknown tokens (first-appearance order), and the total count of tokens encountered."""

    texts: list[str]
    dropped: list[str]
    total: int


@dataclass(frozen=True)
class CitationTokenMap:
    """Bidirectional map between content ids and short `S`-tokens shown to the model.

    The model cites `[^S1]` tokens; storage stays canonical `[^content:<uuid>]`.
    """

    _uuid_by_token: dict[str, UUID]
    _token_by_uuid: dict[UUID, str]

    @classmethod
    def for_sources(cls, ids: Sequence[UUID]) -> "CitationTokenMap":
        """Assign tokens in first-appearance order, de-duplicating repeated ids."""
        uuid_by_token: dict[str, UUID] = {}
        token_by_uuid: dict[UUID, str] = {}
        for content_id in ids:
            if content_id in token_by_uuid:
                continue
            token = f"S{len(token_by_uuid) + 1}"
            token_by_uuid[content_id] = token
            uuid_by_token[token] = content_id
        return cls(uuid_by_token, token_by_uuid)

    def token_for(self, content_id: UUID) -> str:
        return self._token_by_uuid[content_id]

    def tokenize_uuid_markers(self, text: str) -> str:
        """Rewrite `[^content:<uuid>]` markers to `[^S1]` tokens; unknown ids pass through."""

        def replace(match: re.Match[str]) -> str:
            content_id = UUID(match.group("uuid"))
            token = self._token_by_uuid.get(content_id)
            return f"[^{token}]" if token else match.group(0)

        return re.sub(CONTENT_CITATION_PATTERN, replace, text)

    def detokenize_all(self, texts: Sequence[str]) -> DetokenizeResult:
        """Rewrite `[^S1]` tokens back to canonical `[^content:<uuid>]` across several texts.

        The token count comes for free from the single rewrite pass — the replace closure fires
        once per token — so callers never need a second scan to learn how many citations appeared.
        Unknown tokens are dropped from the text and returned de-duplicated in first-appearance order.
        """
        detokenized: list[str] = []
        dropped: list[str] = []
        total = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal total
            total += 1
            token = f"S{match.group('n')}"
            content_id = self._uuid_by_token.get(token)
            if content_id is None:
                if token not in dropped:
                    dropped.append(token)
                return ""
            return f"[^content:{content_id}]"

        for text in texts:
            detokenized.append(re.sub(RESEARCH_TOKEN_PATTERN, replace, text))

        return DetokenizeResult(texts=detokenized, dropped=dropped, total=total)

    def detokenize(self, text: str) -> tuple[str, list[str]]:
        """Rewrite `[^S1]` tokens back to canonical `[^content:<uuid>]`, dropping unknown tokens.

        Returns the rewritten text and the de-duplicated unknown tokens in first-appearance order.
        """
        result = self.detokenize_all([text])
        return result.texts[0], result.dropped


class IndexingID(BaseModel):
    organization_id: UUID
    source_id: str

    async def fetch_content(self, using_db: BaseDBAsyncClient | None = None):
        return await Content.get_to_index(self, using_db=using_db)

    async def fetch_indexer(self, using_db: BaseDBAsyncClient | None = None):
        content = await self.fetch_content(using_db=using_db)
        return ContentIndexer(content)


@dataclass
class SearchableData:
    title: str
    index_content: str
    url: str
    author: str | None = None
    preview_content: str | None = None


@dataclass
class IndexMetadata:
    category: ContentCategory
    content_type: ContentType
    force_sharing: Sharing | None = None
    default_sharing: Sharing | None = None
    allowed_user_ids: list[UUID] | None = None
    add_user_ids: list[UUID] | None = None
    remove_user_ids: list[UUID] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tags: list[str] = field(default_factory=list)
    lookup_key: str | None = None
    lookup_priority: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        category: ContentCategory,
        content_type: ContentType,
        force_sharing: Sharing | None = None,
        default_sharing: Sharing | None = None,
        allowed_user_ids: list[UUID] | None = None,
        add_user_ids: list[UUID] | None = None,
        remove_user_ids: list[UUID] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        tags: list[str] = [],
        lookup_key: str | None = None,
        lookup_priority: int = 0,
        **kwargs: Any,
    ) -> None:
        if force_sharing is not None and default_sharing is not None:
            raise ValueError("Cannot set both force_sharing and default_sharing")

        self.category = category
        self.content_type = content_type
        self.force_sharing = force_sharing
        self.default_sharing = default_sharing
        self.allowed_user_ids = allowed_user_ids
        self.add_user_ids = add_user_ids
        self.remove_user_ids = remove_user_ids
        self.created_at = created_at
        self.updated_at = updated_at
        self.tags = tags
        self.lookup_key = lookup_key
        self.lookup_priority = lookup_priority
        self.extras = kwargs


class ContentFilters:
    private: ClassVar[Q] = Q(sharing=Sharing.PRIVATE)
    organization: ClassVar[Q] = Q(sharing=Sharing.ORGANIZATION)

    @classmethod
    def by_content_type(cls, content_type: ContentType) -> Q:
        return Q(content_type=content_type)

    @classmethod
    def by_accessor(cls, user_id: UUID) -> Q:
        return Q(allowed_user_ids__contains=[str(user_id)])

    @classmethod
    def by_organization(cls, organization_id: UUID) -> Q:
        return Q(organization_id=organization_id)

    @classmethod
    def by_metadata(cls, key: str, value: Any) -> Q:
        return Q(metadata__contains={key: value})

    @classmethod
    def by_source_id_in(cls, source_ids: list[str]) -> Q:
        return Q(source_id__in=source_ids)

    @classmethod
    def by_source_id_startswith(cls, prefix: str) -> Q:
        return Q(source_id__startswith=prefix)


class Content(TaggableMixin, RecordModel):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls not in content_model_registry:
            content_model_registry.append(cls)

    category = fields.CharEnumField(ContentCategory, max_length=255)
    source_id = fields.TextField()
    source_url = fields.TextField()
    content_type = fields.CharEnumField(ContentType, max_length=255)
    sharing = fields.CharEnumField(Sharing, default=Sharing.PRIVATE, max_length=255)
    allowed_user_ids: list[str] = JSONField[list[str]](default=list)  # Using strings for faster and simpler querying
    title = fields.TextField(description="protected_column")
    title_normalized = fields.TextField(description="protected_column")
    author: str | None = fields.TextField(null=True)
    author_normalized: str | None = fields.TextField(null=True)
    preview_content: str | None = fields.TextField(null=True, description="protected_column")
    preview_content_normalized: str | None = fields.TextField(null=True, description="protected_column")
    index_content = fields.TextField(description="protected_column")
    metadata: dict[str, Any] = JSONField(default={})
    embedding = VectorField(vector_size=EMBEDDING_DIMENSION, default=[0.0] * EMBEDDING_DIMENSION)
    text_search = TSVectorField(null=True, store=True, description="protected_column")
    last_indexed_at = fields.DatetimeField(auto_now_add=True)
    lookup_key: str | None = fields.TextField(null=True)
    lookup_priority: int = fields.IntField(default=0)
    is_ai_excluded = fields.BooleanField(default=False)
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    filters = ContentFilters()

    class Meta:
        ordering = ["-last_indexed_at"]
        indexes = [
            GinIndex(fields=("text_search",), fastupdate=False),
            GinIndex(fields=("allowed_user_ids",)),
            ("source_id",),
            ("organization_id", "sharing"),
            PrefixIndex(fields=("organization_id", "source_id"), opclasses={"source_id": "text_pattern_ops"}),
            GinIndex(fields=("author_normalized",), opclass="gin_trgm_ops"),
            HnswIndex(fields=("embedding",)),
        ]
        unique_together = ("organization_id", "source_id")

    @classmethod
    def get_by_indexing_id(cls, indexing_id: IndexingID, using_db: BaseDBAsyncClient | None = None):
        return cls.filter(
            organization_id=indexing_id.organization_id,
            source_id=indexing_id.source_id,
        ).using_db(using_db)

    @classmethod
    async def get_to_index(cls, indexing_id: IndexingID, using_db: BaseDBAsyncClient | None = None):
        result = await cls.get_or_init(
            organization_id=indexing_id.organization_id,
            source_id=indexing_id.source_id,
            using_db=using_db,
        )
        await result.fetch_related("organization")
        return result

    @property
    def source_global_id(self):
        return GlobalID.parse(self.source_id)

    async def fetch_source(self, using_db: BaseDBAsyncClient | None = None) -> RecordModel | None:
        """Fetch the actual source object that this Content represents."""
        return await self.source_global_id.get_or_none(using_db=using_db)

    @property
    def is_orphaned(self):
        return self.sharing.is_private and len(self.allowed_user_ids) == 0

    @property
    def indexer(self):
        return ContentIndexer(self)

    async def save(self, *args, **kwargs):
        # Ensure normalized fields are populated before save because they are required for indexes
        if not self.title_normalized:
            self.title_normalized = normalize_text(self.title) or ""
        if not self.author_normalized and self.author:
            self.author_normalized = normalize_text(self.author)
        if not self.preview_content_normalized and self.preview_content:
            self.preview_content_normalized = normalize_text(self.preview_content)

        update_fields = kwargs.pop("update_fields", None)

        if update_fields is not None:
            # Exclude generated fields from update_fields which will be updated automatically
            update_fields = set(update_fields) - {"text_search"}
        else:
            update_fields = self._meta.fields.copy()

            for field_name, field in self._meta.fields_map.items():
                # Skip generated fields and related models
                if field.generated or hasattr(field, "related_model") or field.pk:
                    update_fields.discard(field_name)

        kwargs["update_fields"] = update_fields
        # Set force_create if the object is not saved in the database
        # This is necessary to use update_fields when creating a new record with Model.save()
        if not self._saved_in_db:
            kwargs["force_create"] = True
        return await super().save(*args, **kwargs)

    def add_user(self, user_id: UUID):
        self.allowed_user_ids = list(set(self.allowed_user_ids) | {str(user_id)})

    def remove_user(self, user_id: UUID):
        self.allowed_user_ids = list(set(self.allowed_user_ids) - {str(user_id)})

    def can_be_accessed_by(self, user_id: UUID):
        return self.sharing.is_organization or str(user_id) in self.allowed_user_ids

    @staticmethod
    def deduplicate_by_lookup_key(results: list[Any]) -> list[Any]:
        """Collapse recurring-meeting instances (and similar grouped content) into one result.

        Content with the same lookup_key is deduplicated, keeping the instance with the
        highest lookup_priority. Content without a lookup_key passes through unchanged.
        Works with both Content and ContentLookup objects.
        """
        seen_keys: dict[str, tuple[Any, int]] = {}
        deduped: list[Any] = []

        for content in results:
            if content.lookup_key is None:
                deduped.append(content)
                continue

            if content.lookup_key not in seen_keys:
                deduped_index = len(deduped)
                seen_keys[content.lookup_key] = (content, deduped_index)
                deduped.append(content)
            else:
                existing_content, existing_index = seen_keys[content.lookup_key]
                if content.lookup_priority > existing_content.lookup_priority:
                    deduped[existing_index] = content
                    seen_keys[content.lookup_key] = (content, existing_index)

        return deduped


class ContentLookup(RecordModel):
    content: fields.OneToOneRelation[Content] = fields.OneToOneField(
        "convictional.Content", on_delete=fields.CASCADE, related_name="content_lookup"
    )
    content_id: Annotated[UUID, "foreign key to content"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField(
        "convictional.Organization", on_delete=fields.CASCADE
    )
    organization_id: Annotated[UUID, "foreign key to organization"]
    source_id = fields.TextField()
    source_url = fields.TextField()
    title = fields.TextField(description="protected_column")
    title_normalized = fields.TextField(description="protected_column")
    author: str | None = fields.TextField(null=True)
    author_normalized: str | None = fields.TextField(null=True)
    preview_content_normalized: str | None = fields.TextField(null=True, description="protected_column")
    content_type = fields.CharEnumField(ContentType, max_length=255)
    sharing = fields.CharEnumField(Sharing, default=Sharing.PRIVATE, max_length=255)
    allowed_user_ids: list[str] = JSONField[list[str]](default=list)
    metadata: dict[str, Any] = JSONField(default={})
    lookup_key: str | None = fields.TextField(null=True)
    lookup_priority: int = fields.IntField(default=0)
    lookup_search = TSVectorField(generated=True, store=True, description="protected_column")

    SYNCED_FIELDS = (
        "organization_id",
        "source_id",
        "source_url",
        "title",
        "title_normalized",
        "author",
        "author_normalized",
        "preview_content_normalized",
        "content_type",
        "sharing",
        "allowed_user_ids",
        "metadata",
        "lookup_key",
        "lookup_priority",
        "created_at",
        "updated_at",
    )

    class Meta:
        indexes = [
            GinIndex(fields=("lookup_search",), fastupdate=False),
            GinIndex(fields=("allowed_user_ids",)),
            GinIndex(fields=("author_normalized",), opclass="gin_trgm_ops"),
            ("organization_id", "sharing"),
        ]

    @property
    def source_global_id(self):
        return GlobalID.parse(self.source_id)

    def sync_from_content(self, content: "Content"):
        for field_name in self.SYNCED_FIELDS:
            setattr(self, field_name, getattr(content, field_name))

    async def save(self, *args, **kwargs):
        update_fields = kwargs.pop("update_fields", None)

        if update_fields is not None:
            update_fields = set(update_fields) - {"lookup_search"}
        else:
            update_fields = self._meta.fields.copy()
            for field_name, field in self._meta.fields_map.items():
                if field.generated or hasattr(field, "related_model") or field.pk:
                    update_fields.discard(field_name)

        kwargs["update_fields"] = update_fields
        if not self._saved_in_db:
            kwargs["force_create"] = True
        return await super().save(*args, **kwargs)


@dataclass
class ContentIndexer:
    content: Content

    async def index(self, data: SearchableData, metadata: IndexMetadata):
        await self._update_fields(data, metadata)

        if not self.content.index_content:
            logger.info("Skipping indexing for content with empty index_content")
            await self._sync_content_lookup()
            return

        await self._generate_embeddings()

        try:
            await self.content.save()
        except asyncpg.exceptions.ProgramLimitExceededError:
            logger.warning("Content exceeds tsvector limit, saving with further truncated index_content")
            self.content.index_content = self.content.index_content[:INDEX_CONTENT_FALLBACK_MAX_LENGTH]
            await self.content.save()

        await self._sync_content_lookup()

    async def _update_fields(self, data: SearchableData, metadata: IndexMetadata):
        # Update fields from data
        self.content.title = self._sanitize_text(data.title)
        self.content.index_content = self._truncate_index_content(self._sanitize_text(data.index_content))
        self.content.preview_content = self._sanitize_text(data.preview_content)
        self.content.author = self._sanitize_text(data.author) or self.content.author
        self.content.source_url = data.url

        self.content.title_normalized = normalize_text(self.content.title) or ""
        self.content.author_normalized = normalize_text(self.content.author)
        self.content.preview_content_normalized = normalize_text(self.content.preview_content)

        # Update metadata fields
        self.content.content_type = metadata.content_type
        self.content.category = metadata.category
        self.content.tags = metadata.tags or self.content.tags or []
        self.content.metadata = metadata.extras or self.content.metadata or {}
        if metadata.default_sharing is not None and self.content.is_new:
            self.content.sharing = metadata.default_sharing
        elif metadata.force_sharing is not None:
            self.content.sharing = metadata.force_sharing

        # Update allowed user ids
        if metadata.allowed_user_ids is not None:
            self.content.allowed_user_ids = [str(user_id) for user_id in metadata.allowed_user_ids]
        if metadata.add_user_ids is not None:
            for user_id in metadata.add_user_ids:
                self.content.add_user(user_id)
        if metadata.remove_user_ids is not None:
            for user_id in metadata.remove_user_ids:
                self.content.remove_user(user_id)

        # Update timestamps
        now = datetime.now(UTC)
        self.content.created_at = metadata.created_at or now
        self.content.updated_at = metadata.updated_at or now
        self.content.last_indexed_at = now

        # Update lookup fields
        self.content.lookup_key = metadata.lookup_key
        self.content.lookup_priority = metadata.lookup_priority

    def _sanitize_text(self, text: str | None):
        if text is None:
            return None

        return text.replace("\x00", "")

    def _truncate_index_content(self, text: str) -> str:
        return text[:INDEX_CONTENT_MAX_LENGTH]

    async def _sync_content_lookup(self):
        # Content is unsaved when index_content is empty (early return skips content.save()).
        # Syncing a lookup against an unsaved content_id would violate contentlookup_content_id_fkey.
        if self.content.is_new:
            return

        # Lookup is secondary to content indexing — don't fail the index if this breaks
        try:
            lookup = await ContentLookup.get_or_init(content_id=self.content.id)
            lookup.sync_from_content(self.content)
            await lookup.save()
        except (tortoise.exceptions.BaseORMException, asyncpg.PostgresError):
            logger.exception("Failed to sync content lookup entry")

    async def _generate_embeddings(self):
        chunks = chunk_string(self.content.index_content, EMBEDDING_TOKENS, encoding=EMBEDDING_ENCODING)
        self.content.embedding = await self.content.organization.vectors.embed(chunks[0])


@dataclass
class BaseSearch:
    organization: Organization
    query: str
    user: User | None = None
    limit: int = RESULTS_PER_TYPE_LIMIT
    starts_at: datetime | None = None
    ends_at: datetime | None = None


@dataclass
class ContentSearchQuery(BaseSearch):
    content_types: set[ContentType] | None = None
    exclude_source_urls: list[str] = field(default_factory=list)
    embedding_query: str = field(default="", init=False, repr=False)

    # Position of `limit` within the params list built by _init_query_state. near_misses()
    # overwrites this slot; the constant keeps that coupling from silently breaking if the
    # param layout below ever changes.
    _LIMIT_PARAM_INDEX: ClassVar[int] = 2

    async def _get_embedding_query(self) -> str:
        embedding_values = await self.organization.vectors.embed(self.query)
        return "[" + ", ".join(str(value) for value in embedding_values) + "]"

    def _text_query(self) -> str:
        return " OR ".join(self.query.split())

    def normalized_query(self) -> str:
        return self._text_query()

    def _init_query_state(self) -> None:
        self.connection = Tortoise.get_connection("default")
        self.table_name = Content._meta.db_table
        self._params: list = [self._text_query(), self.embedding_query, self.limit]
        self._where_conditions: list[str] = []

    def _build_where_clauses(self) -> tuple[str, str]:
        where_clause = f"WHERE {' AND '.join(self._where_conditions)}" if self._where_conditions else ""
        text_search_condition = "c.text_search @@ websearch_to_tsquery('english', $1)"
        text_where_clause = (
            f"{where_clause} AND {text_search_condition}"
            if self._where_conditions
            else f"WHERE {text_search_condition}"
        )
        return where_clause, text_where_clause

    def _apply_access(self) -> None:
        self._params.append(str(self.organization.id))
        self._where_conditions.append(f"c.organization_id = ${len(self._params)}")

        if not self.user:
            self._where_conditions.append(f"c.sharing = '{Sharing.ORGANIZATION.value}'")
        else:
            self._params.append(str(self.user.id))
            self._where_conditions.append(
                f"(c.sharing = '{Sharing.ORGANIZATION.value}' OR c.allowed_user_ids ? ${len(self._params)})"
            )

    def _apply_exclusions(self) -> None:
        for excluded_url in self.exclude_source_urls:
            self._params.append(excluded_url)
            self._where_conditions.append(f"c.source_url <> ${len(self._params)}")

    def _apply_date_range(self) -> None:
        # Filter on updated_at, not created_at: created_at is when the Content row was first
        # indexed, which for a meeting is when it was scheduled (often weeks before it happens),
        # so a date-bounded search would miss the meeting for the window it actually occurred in.
        # updated_at tracks last meaningful activity (see indexing_activity_at) and is the same
        # signal search already ranks on, so filtering and ranking stay consistent.
        if self.starts_at:
            if self.starts_at.tzinfo is None:
                self.starts_at = self.starts_at.replace(tzinfo=UTC)
            else:
                self.starts_at = self.starts_at.astimezone(UTC)
            self._params.append(self.starts_at)
            self._where_conditions.append(f"c.updated_at >= ${len(self._params)}")

        if self.ends_at:
            if self.ends_at.tzinfo is None:
                self.ends_at = self.ends_at.replace(tzinfo=UTC)
            else:
                self.ends_at = self.ends_at.astimezone(UTC)
            self._params.append(self.ends_at)
            self._where_conditions.append(f"c.updated_at <= ${len(self._params)}")

    def _apply_content_type(self) -> None:
        if self.content_types:
            if len(self.content_types) == 1:
                self._params.append(next(iter(self.content_types)).value)
                self._where_conditions.append(f"c.content_type = ${len(self._params)}")
            else:
                placeholders = []
                for ct in self.content_types:
                    self._params.append(ct.value)
                    placeholders.append(f"${len(self._params)}")
                self._where_conditions.append(f"c.content_type IN ({', '.join(placeholders)})")


@dataclass
class ContentResearchQuery(ContentSearchQuery):
    ai_filtered: bool = True
    minimum_results_with_exact_matching: int = RESULTS_PER_TYPE_LIMIT * 2

    async def execute(self) -> list[Content]:
        self.embedding_query = await self._get_embedding_query()
        results = await self._execute_with_where_clauses(
            self._apply_exclusions, self._apply_exact_match_phrases, self._apply_date_range, self._apply_content_type
        )

        if len(results) < self.minimum_results_with_exact_matching:
            additional_results = await self._execute_with_where_clauses(
                self._apply_exclusions, self._apply_date_range, self._apply_content_type
            )
            existing_ids = {result.id for result in results}
            for result in additional_results:
                if result.id not in existing_ids:
                    results.append(result)
                    existing_ids.add(result.id)
                    if len(results) >= self.limit:
                        break

        return results

    async def _execute_with_where_clauses(self, *args: Callable):
        self._init_query_state()

        self._apply_access()
        for apply_where_clause in args:
            apply_where_clause()

        where_clause, text_where_clause = self._build_where_clauses()

        raw_results = await self.connection.execute_query_dict(
            f"""
            WITH vector_matches AS (
                SELECT id, (1 - (embedding <=> $2) / 2) AS similarity
                FROM {self.table_name} c
                {where_clause}
                ORDER BY embedding <=> $2
                LIMIT {settings.content_search_max_vector_matches}
            ),
            text_matches AS (
                SELECT id, ts_rank(text_search, websearch_to_tsquery('english', $1)) AS text_rank
                FROM {self.table_name} c
                {text_where_clause}
                ORDER BY text_rank DESC
                LIMIT {settings.content_search_max_text_matches}
            ),
            scored_matches AS (
                SELECT id, similarity, 0::float AS text_rank FROM vector_matches
                UNION ALL
                SELECT id, 0::float AS similarity, text_rank FROM text_matches
            ),
            aggregated_scores AS (
                SELECT
                    id,
                    MAX(similarity) AS similarity,
                    MAX(text_rank) AS text_rank
                FROM scored_matches
                GROUP BY id
            ),
            ranked_results AS (
                SELECT
                    c.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.category
                        ORDER BY (
                            COALESCE(a.similarity, 0) * 0.7 +
                            COALESCE(a.text_rank, 0) * 0.3
                        ) DESC
                    ) AS rn
                FROM aggregated_scores a
                JOIN {self.table_name} c ON c.id = a.id
            )
            SELECT *
            FROM ranked_results
            WHERE rn <= $3;
            """,
            self._params,
        )

        return [Content(**result) for result in raw_results]

    def _apply_exclusions(self) -> None:
        if self.ai_filtered:
            self._where_conditions.append("c.is_ai_excluded = FALSE")

            self._params.append(f"{settings.product_name} <{settings.research_email_from}>%")
            self._where_conditions.append(
                f"(c.author_normalized IS NULL OR c.author_normalized NOT ILIKE ${len(self._params)})"
            )

        super()._apply_exclusions()

    def _apply_exact_match_phrases(self) -> None:
        exact_match_phrases: list[str] = re.findall(r'"[^"]+?"', self.query)
        for phrase in exact_match_phrases:
            self._params.append(phrase.strip('"'))
            self._where_conditions.append(f"c.text_search @@ websearch_to_tsquery('english', ${len(self._params)})")


SERP_VECTOR_WEIGHT = 0.2
SERP_TEXT_WEIGHT = 0.3
SERP_TITLE_WEIGHT = 0.5
SERP_RECENCY_HALF_LIFE_DAYS = 14
SERP_RECENCY_MAX_BOOST = 9.0
SERP_HERO_RELEVANCE_GAP = 0.05  # Derived from production analysis — catches cases like 0.77 vs 0.65
SERP_MAX_HEROES = 3
# Queries with no real match in the corpus (e.g. names not present) still produce scores
# up to ~0.124 from pure recency-boosted vector similarity. 0.125 is the lowest flat floor
# that reliably zeroes those out while preserving incidental-but-real name mentions that
# score in the 0.125–0.15 band. Intentionally loose to keep deep/name-match recall.
SERP_RELEVANCE_FLOOR = 0.125
# Shared by ContentSerpQuery and ContentLookupQuery — these penalize signal quality,
# not recency, so they belong in the stored relevance_score (hero promotion honors them).
AUTOMATED_SENDER_WEIGHT = 0.25
CALENDAR_INVITE_WEIGHT = 0.4
SECONDS_PER_DAY = 86400
# Extra rows fetched (without the relevance floor) to surface "just missed the floor" candidates.
NEAR_MISS_BUFFER = 20

# SERP assembly knobs. The /api/search router and the search diagnostic job both run a search
# through run_serp_search() so the limits, default content types, dedup, and hero promotion
# stay defined in one place and can't drift between the live endpoint and the diagnostic.
SERP_RESULT_LIMIT = 30
SERP_FETCH_MULTIPLIER = 2
SERP_DEFAULT_CONTENT_TYPES: set[ContentType] = {
    ContentType.MEETING,
    ContentType.POST,
    ContentType.GOAL,
    ContentType.DOCUMENT,
    ContentType.EMAIL_THREAD,
    ContentType.CHAT,
}


@dataclass
class TargetDiagnosis:
    """Where a specific expected result dropped out of the pipeline, stage by stage."""

    content_id: UUID
    exists: bool
    accessible: bool | None = None
    content_type_included: bool | None = None
    in_date_range: bool | None = None
    text_matches: bool | None = None
    similarity: float | None = None
    text_rank: float | None = None
    title_rank: float | None = None
    relevance_score: float | None = None
    above_floor: bool | None = None
    rank: int | None = None
    verdict: str = ""


@dataclass
class SearchDiagnostics:
    """Self-contained breakdown of a single search run — readable without DB access."""

    query: str
    normalized_query: str
    tsquery: str
    funnel: dict[str, int]
    result_count: int
    results: list[dict]
    near_misses: list[dict]
    targets: list[TargetDiagnosis]
    # True when the (empty) full-text match fell back to a title/author trigram substring match.
    # `tsquery` still shows the real generated tsquery, so this is a separate, honest signal —
    # an empty tsquery here means an all-stopword query; a non-empty one means full-text simply
    # matched nothing (e.g. a mid-word substring) and the fallback found it.
    fallback_used: bool = False


@dataclass
class ContentSerpQuery(ContentSearchQuery):
    collect_diagnostics: bool = False
    relevance_scores: dict[UUID, float] = field(default_factory=dict, init=False, repr=False)
    component_scores: dict[UUID, dict[str, float | None]] = field(default_factory=dict, init=False, repr=False)
    hero_count: int = field(default=0, init=False, repr=False)

    @staticmethod
    def _relevance_expr(similarity: str, text_rank: str, title_rank: str) -> str:
        """The relevance score as SQL, parameterized by the column/expression for each signal.

        Both the production ranking query and the single-row diagnostic probe build their
        score from this one definition, so the weights and signal penalties can't drift apart.
        """
        return (
            f"(({similarity}) * {SERP_VECTOR_WEIGHT}"
            f" + ({text_rank}) * {SERP_TEXT_WEIGHT}"
            f" + ({title_rank}) * {SERP_TITLE_WEIGHT})"
            f" * CASE WHEN (c.metadata->>'is_automated_sender')::boolean"
            f" THEN {AUTOMATED_SENDER_WEIGHT} ELSE 1.0 END"
            f" * CASE WHEN (c.metadata->>'has_calendar_invite')::boolean"
            f" THEN {CALENDAR_INVITE_WEIGHT} ELSE 1.0 END"
        )

    @staticmethod
    def _recency_expr() -> str:
        decay_seconds = SERP_RECENCY_HALF_LIFE_DAYS * SECONDS_PER_DAY
        return (
            f"(1.0 + {SERP_RECENCY_MAX_BOOST} / (1.0 + EXTRACT(EPOCH FROM (NOW() - c.updated_at)) / {decay_seconds}))"
        )

    async def _prepare(self) -> None:
        if not self.embedding_query:
            self.embedding_query = await self._get_embedding_query()
        self._init_query_state()
        self._apply_access()
        self._apply_exclusions()
        self._apply_date_range()
        self._apply_content_type()

    def _scored_query(self, *, apply_floor: bool) -> str:
        where_clause, text_where_clause = self._build_where_clauses()
        relevance = self._relevance_expr(
            "COALESCE(a.similarity, 0)", "COALESCE(a.text_rank, 0)", "COALESCE(a.title_rank, 0)"
        )
        recency = self._recency_expr()
        # Component scores are already computed in aggregated_scores; only project them when
        # diagnosing so the production hot path is byte-for-byte unchanged.
        diag_select = (
            ", a.similarity AS _diag_similarity, a.text_rank AS _diag_text_rank, a.title_rank AS _diag_title_rank"
            if self.collect_diagnostics
            else ""
        )
        floor_clause = f"WHERE c.relevance_score >= {SERP_RELEVANCE_FLOOR}" if apply_floor else ""
        return f"""
            WITH vector_matches AS (
                SELECT id, (1 - (embedding <=> $2) / 2) AS similarity
                FROM {self.table_name} c
                {where_clause}
                ORDER BY embedding <=> $2
                LIMIT {settings.content_search_max_vector_matches}
            ),
            text_matches AS (
                SELECT
                    c.id,
                    ts_rank(c.text_search, websearch_to_tsquery('english', $1), 1) AS text_rank,
                    ts_rank(
                        setweight(to_tsvector('english', COALESCE(c.title, '')), 'A'),
                        websearch_to_tsquery('english', $1)
                    ) AS title_rank
                FROM {self.table_name} c
                {text_where_clause}
                ORDER BY text_rank DESC
                LIMIT {settings.content_search_max_text_matches}
            ),
            scored_matches AS (
                SELECT id, similarity, 0::float AS text_rank, 0::float AS title_rank
                FROM vector_matches
                UNION ALL
                SELECT id, 0::float AS similarity, text_rank, title_rank
                FROM text_matches
            ),
            aggregated_scores AS (
                SELECT
                    id,
                    MAX(similarity) AS similarity,
                    MAX(text_rank) AS text_rank,
                    MAX(title_rank) AS title_rank
                FROM scored_matches
                GROUP BY id
            ),
            scored_final AS (
                SELECT c.*{diag_select}, ({relevance}) AS relevance_score
                FROM aggregated_scores a
                JOIN {self.table_name} c ON c.id = a.id
            )
            SELECT *
            FROM scored_final c
            {floor_clause}
            ORDER BY c.relevance_score * {recency} DESC
            LIMIT $3;
        """

    async def execute(self) -> list[Content]:
        await self._prepare()
        raw_results = await self.connection.execute_query_dict(self._scored_query(apply_floor=True), self._params)

        self.relevance_scores.clear()
        self.component_scores.clear()
        results = []
        for row in raw_results:
            score = row.pop("relevance_score", None)
            similarity = row.pop("_diag_similarity", None)
            text_rank = row.pop("_diag_text_rank", None)
            title_rank = row.pop("_diag_title_rank", None)
            content = Content(**row)
            if score is not None:
                self.relevance_scores[content.id] = score
            if self.collect_diagnostics:
                self.component_scores[content.id] = {
                    "similarity": similarity,
                    "text_rank": text_rank,
                    "title_rank": title_rank,
                    "relevance_score": score,
                }
            results.append(content)
        return results

    def promote_heroes(self, results: list[Content]) -> list[Content]:
        if not results or not self.relevance_scores:
            self.hero_count = 0
            return results

        result_ids = {r.id for r in results}
        scoped_scores = {k: v for k, v in self.relevance_scores.items() if k in result_ids}
        if not scoped_scores:
            self.hero_count = 0
            return results

        # Top N by pure relevance — these are the ideal top results ignoring recency
        by_relevance = sorted(scoped_scores, key=lambda k: scoped_scores[k], reverse=True)
        hero_ids = by_relevance[:SERP_MAX_HEROES]

        # Only reorder if a hero candidate has significantly higher relevance than
        # the current result occupying that position
        promoted: list[Content] = []
        for i, hero_id in enumerate(hero_ids):
            if i >= len(results):
                break
            current_id = results[i].id
            if hero_id == current_id:
                promoted.append(results[i])
                continue
            # Fallback to 0 if current_id missing — biases toward promotion, the safe default
            gap = scoped_scores[hero_id] - scoped_scores.get(current_id, 0)
            if gap <= SERP_HERO_RELEVANCE_GAP:
                continue
            hero = next(r for r in results if r.id == hero_id)
            promoted.append(hero)

        self.hero_count = len(promoted)

        if not promoted or all(p.id == r.id for p, r in zip(promoted, results)):
            return results

        promoted_ids = {h.id for h in promoted}
        remaining = [r for r in results if r.id not in promoted_ids]
        return promoted + remaining

    #
    # Diagnostics — used by the search diagnostic job (app/jobs/search.py). These read the
    # same corpus the production query reads and reuse the factored scoring fragments, so the
    # report localizes failures without drifting from real ranking behavior.
    #

    async def generated_tsquery(self) -> str:
        rows = await Tortoise.get_connection("default").execute_query_dict(
            "SELECT websearch_to_tsquery('english', $1)::text AS tsq", [self._text_query()]
        )
        return rows[0]["tsq"]

    async def funnel(self) -> dict[str, int]:
        """Population remaining after each successive filter, so the stage where it collapses to
        zero is visible. Reuses the production access clause (`_build_access_clause`) and the
        text-match predicate so the counts mirror the live query. Each filter is its own stage —
        the content_type filter is kept separate from organization_total so a collapse there is
        visible rather than folded into the org count."""
        params: list = [str(self.organization.id)]

        if self.content_types:
            type_values = ", ".join(f"'{ct.value}'" for ct in self.content_types)
            type_filter = f"c.content_type IN ({type_values})"
        else:
            type_filter = "TRUE"

        access_clause, access_params = _build_access_clause(self.user, len(params))
        params.extend(access_params)

        params.append(self._text_query())
        text_filter = f"c.text_search @@ websearch_to_tsquery('english', ${len(params)})"

        rows = await Tortoise.get_connection("default").execute_query_dict(
            f"""
            SELECT
                COUNT(*) AS organization_total,
                COUNT(*) FILTER (WHERE {type_filter}) AS matching_content_types,
                COUNT(*) FILTER (WHERE {type_filter} AND {access_clause}) AS accessible,
                COUNT(*) FILTER (WHERE {type_filter} AND {access_clause} AND {text_filter}) AS text_matching
            FROM {Content._meta.db_table} c
            WHERE c.organization_id = $1
            """,
            params,
        )
        row = rows[0]
        return {
            key: row[key] for key in ("organization_total", "matching_content_types", "accessible", "text_matching")
        }

    async def near_misses(self) -> list[dict]:
        """Candidates that scored but fell below the relevance floor — the common
        'scored 0.11, floor is 0.125' case that otherwise looks like 'no match at all'."""
        await self._prepare()
        self._params[self._LIMIT_PARAM_INDEX] = self.limit + NEAR_MISS_BUFFER  # widen the LIMIT ($3) past the floor
        rows = await self.connection.execute_query_dict(self._scored_query(apply_floor=False), self._params)
        misses = []
        for row in rows:
            score = row.get("relevance_score")
            if score is not None and score < SERP_RELEVANCE_FLOOR:
                # Titles are deliberately omitted — they often carry the sensitive content
                # itself and would leak into log aggregation. ID + type + score is enough to act on.
                misses.append(
                    {
                        "content_id": row["id"],
                        "content_type": row.get("content_type"),
                        "relevance_score": score,
                    }
                )
        return misses

    def _in_date_range(self, updated_at: datetime) -> bool:
        # Mirrors _apply_date_range, which bounds on updated_at (see the note there).
        starts_at, ends_at = self.starts_at, self.ends_at
        if starts_at:
            starts_at = starts_at.replace(tzinfo=UTC) if starts_at.tzinfo is None else starts_at.astimezone(UTC)
            if updated_at < starts_at:
                return False
        if ends_at:
            ends_at = ends_at.replace(tzinfo=UTC) if ends_at.tzinfo is None else ends_at.astimezone(UTC)
            if updated_at > ends_at:
                return False
        return True

    async def diagnose_target(self, content_id: UUID, result_ids: list[UUID] | None = None) -> TargetDiagnosis:
        content = await Content.filter(id=content_id, organization_id=self.organization.id).first()
        if not content:
            return TargetDiagnosis(
                content_id=content_id, exists=False, verdict="not found in Content for this organization"
            )

        diagnosis = TargetDiagnosis(content_id=content_id, exists=True)
        diagnosis.accessible = (
            content.can_be_accessed_by(self.user.id) if self.user else content.sharing.is_organization
        )
        diagnosis.content_type_included = content.content_type in self.content_types if self.content_types else True
        diagnosis.in_date_range = self._in_date_range(content.updated_at)

        if not self.embedding_query:
            self.embedding_query = await self._get_embedding_query()
        text_query = self._text_query()
        relevance = self._relevance_expr(
            "(1 - (c.embedding <=> $2) / 2)",
            "ts_rank(c.text_search, websearch_to_tsquery('english', $1), 1)",
            "ts_rank(setweight(to_tsvector('english', COALESCE(c.title, '')), 'A'),"
            " websearch_to_tsquery('english', $1))",
        )
        rows = await Tortoise.get_connection("default").execute_query_dict(
            f"""
            SELECT
                (1 - (c.embedding <=> $2) / 2) AS similarity,
                ts_rank(c.text_search, websearch_to_tsquery('english', $1), 1) AS text_rank,
                ts_rank(
                    setweight(to_tsvector('english', COALESCE(c.title, '')), 'A'),
                    websearch_to_tsquery('english', $1)
                ) AS title_rank,
                (c.text_search @@ websearch_to_tsquery('english', $1)) AS text_matches,
                ({relevance}) AS relevance_score
            FROM {Content._meta.db_table} c
            WHERE c.id = $3
            """,
            [text_query, self.embedding_query, str(content_id)],
        )
        if rows:
            row = rows[0]
            diagnosis.similarity = row["similarity"]
            diagnosis.text_rank = row["text_rank"]
            diagnosis.title_rank = row["title_rank"]
            diagnosis.text_matches = row["text_matches"]
            score = row["relevance_score"]
            # A row with no embedding (default zero vector) makes cosine distance NaN, which
            # poisons relevance_score. Surface that as its own cause rather than letting the
            # Python floor comparison silently report "below floor (nan)".
            if score is not None and score != score:
                diagnosis.relevance_score = None
                diagnosis.above_floor = None
            else:
                diagnosis.relevance_score = score
                diagnosis.above_floor = score is not None and score >= SERP_RELEVANCE_FLOOR

        results_known = result_ids is not None
        if result_ids and content_id in result_ids:
            diagnosis.rank = result_ids.index(content_id)
        diagnosis.verdict = _serp_verdict(diagnosis, results_known)
        return diagnosis


def _serp_verdict(diagnosis: TargetDiagnosis, results_known: bool) -> str:
    if diagnosis.accessible is False:
        return "excluded by access control: sharing is private and user is not in allowed_user_ids"
    if diagnosis.content_type_included is False:
        return "excluded by the content_type filter"
    if diagnosis.in_date_range is False:
        return "excluded by the date-range filter"
    if diagnosis.exists and diagnosis.relevance_score is None:
        return (
            "vector similarity is NaN — content has no embedding (likely never indexed), "
            "so production ranking is unreliable for this row"
        )
    if diagnosis.above_floor is False:
        floor = SERP_RELEVANCE_FLOOR
        return f"scored below the relevance floor ({diagnosis.relevance_score:.4f} < {floor})"
    if not results_known:
        return "passed all gates; not compared against a result set"
    if diagnosis.rank is None:
        return "passed all gates but is absent from the returned set (beyond limit or deduplicated)"
    return f"returned at rank {diagnosis.rank}"


async def run_serp_search(
    *,
    organization: Organization,
    query: str,
    user: User | None,
    content_type: ContentType | None = None,
    collect_diagnostics: bool = False,
) -> tuple[list[Content], ContentSerpQuery]:
    """Run a SERP search end to end (fetch, dedup, hero promotion) and return the assembled
    results alongside the query object. Shared by the /api/search router and the search
    diagnostic job so they exercise identical behavior."""
    search = ContentSerpQuery(
        organization=organization,
        query=query,
        user=user,
        limit=SERP_RESULT_LIMIT * SERP_FETCH_MULTIPLIER,
        content_types={content_type} if content_type else set(SERP_DEFAULT_CONTENT_TYPES),
        collect_diagnostics=collect_diagnostics,
    )
    results = await search.execute()
    results = Content.deduplicate_by_lookup_key(results)[:SERP_RESULT_LIMIT]
    results = search.promote_heroes(results)
    return results, search


async def fetch_content_by_ids(ids: list[UUID], using_db: BaseDBAsyncClient | None = None) -> list[Content]:
    if not ids:
        return []

    results: list[Content] = []
    results.extend(await Content.filter(id__in=ids).using_db(using_db))
    for model in content_model_registry:
        results.extend(await model.filter(id__in=ids).using_db(using_db))
    return results


class ContentResultsMixin(RecordModel):
    content_search: dict[str, Any] = JSONField(default={})
    content_result_ids: list[UUID] = JSONField(default=[])

    class Meta:
        abstract = True

    @property
    def content_search_terms(self):
        return self.content_search.get("query", "")

    async def fetch_content_results(self, using_db: BaseDBAsyncClient | None = None):
        unsorted = await fetch_content_by_ids(self.content_result_ids, using_db)
        return sorted(unsorted, key=lambda content: self.content_result_ids.index(content.id))

    def set_content_search(self, search: BaseSearch, results: Sequence[Content] = []):
        self.content_search = asdict(search)
        self.content_search.pop("organization")
        self.content_search.pop("user")
        self.content_search.pop("embedding_query", None)
        self.content_result_ids = [result.id for result in results]

    async def save_content_search(
        self, search: BaseSearch, results: Sequence[Content], using_db: BaseDBAsyncClient | None = None
    ):
        self.set_content_search(search, results)
        await self.save(update_fields=["content_search", "content_result_ids"], using_db=using_db)


LOOKUP_RECENCY_HALF_LIFE_DAYS = 7
LOOKUP_FETCH_MULTIPLIER = 3
LOOKUP_PERSON_LIMIT = 2
LOOKUP_EXCLUDED_CONTENT_TYPES = [
    ContentType.MEETING_TRANSCRIPT,
    ContentType.POST_COMMENT,
    ContentType.CHAT_HISTORY,
    # Decisions have no nav target of their own and would duplicate the parent
    # resource, so they stay out of the cmd+k typeahead.
    ContentType.DECISION,
]


def _build_access_clause(user: User | None, current_param_num: int) -> tuple[str, list]:
    org_sharing = f"c.sharing = '{Sharing.ORGANIZATION.value}'"

    if not user:
        return org_sharing, []
    else:
        next_param = current_param_num + 1
        return f"({org_sharing} OR c.allowed_user_ids ? ${next_param})", [str(user.id)]


def _build_authors_clause(authors_like: list[str], current_param_num: int) -> tuple[str, list]:
    author_clauses = []
    params = []

    for author in authors_like:
        normalized = normalize_text(author)
        if normalized:
            params.append(f"%{normalized}%")
            param_num = current_param_num + len(params)
            author_clauses.append(f"c.author_normalized LIKE ${param_num}")

    if author_clauses:
        return f"({' OR '.join(author_clauses)})", params

    return "", []


def _build_created_before_clause(created_before: datetime | None, current_param_num: int) -> tuple[str, list]:
    if created_before:
        next_param = current_param_num + 1
        return f"AND c.created_at <= ${next_param}", [created_before]
    return "", []


CONTENTLOOKUP_COLUMNS = ("c.content_id AS id",) + tuple(f"c.{f}" for f in ContentLookup.SYNCED_FIELDS)

# When a query is entirely English stopwords (e.g. "will", "may" — disproportionately common first
# names), websearch_to_tsquery('english', …) is empty and the full-text match returns nothing. When
# the main lookup comes back empty we retry with a title/author trigram substring match. Gated at 3
# chars because a shorter '%xx%' would match almost everything.
STOPWORD_FALLBACK_MIN_LENGTH = 3


@dataclass
class ContentLookupQuery:
    organization: Organization
    query: str
    current_user: User | None = None
    limit: int = 10
    authors_like: list[str] | None = None
    content_types: list[ContentType] | None = None
    created_before: datetime | None = None
    collect_diagnostics: bool = False
    result_scores: dict[UUID, float] = field(default_factory=dict, init=False, repr=False)
    # Set by execute() when the stopword trigram fallback produced the results. The diagnostic
    # probes (funnel/diagnose_target/generated_tsquery) read it so the report reflects the query
    # that actually ran — they assume execute() ran first, which the diagnostic job always does.
    used_trigram_fallback: bool = field(default=False, init=False, repr=False)

    @staticmethod
    def _trigram_match(param: int) -> str:
        """Title/author substring match for the stopword fallback. LIKE metacharacters (\\ % _) in the
        bound value are escaped in SQL so they match literally rather than as wildcards."""
        escaped = f"replace(replace(replace(${param}, '\\', '\\\\'), '%', '\\%'), '_', '\\_')"
        return (
            f"(c.title_normalized ILIKE '%' || {escaped} || '%' OR c.author_normalized ILIKE '%' || {escaped} || '%')"
        )

    @staticmethod
    def _trigram_score(param: int) -> str:
        """Fallback relevance: trigram similarity over title AND author (the columns _trigram_match
        matches), so an author-only hit still ranks instead of collapsing to 0."""
        return (
            f"GREATEST(word_similarity(${param}, c.title_normalized),"
            f" word_similarity(${param}, COALESCE(c.author_normalized, '')))"
        )

    @staticmethod
    def _match_clause(param: int, *, trigram: bool = False) -> str:
        if trigram:
            return ContentLookupQuery._trigram_match(param)
        return f"""
            websearch_to_tsquery('english', ${param})::text != ''
            AND to_tsquery(
              'english',
              websearch_to_tsquery('english', ${param})::text || ':*'
            ) @@ c.lookup_search
        """

    @staticmethod
    def _score_expr(param: int, *, trigram: bool = False) -> str:
        """Lookup relevance as SQL, parameterized by the full-text param position. Shared by
        the production query and the diagnostic probe so the ranking can't drift apart."""
        if trigram:
            core = ContentLookupQuery._trigram_score(param)
        else:
            core = f"""
              CASE
                WHEN websearch_to_tsquery('english', ${param})::text != ''
                THEN ts_rank_cd(
                  c.lookup_search,
                  to_tsquery('english', websearch_to_tsquery('english', ${param})::text || ':*')
                )
                ELSE 0
              END
            """
        decay_seconds = LOOKUP_RECENCY_HALF_LIFE_DAYS * SECONDS_PER_DAY
        recency_multiplier = f"(1.0 + 19.0 / (1.0 + EXTRACT(EPOCH FROM (NOW() - c.updated_at)) / {decay_seconds}))"
        return f"""
            ({core}) * {recency_multiplier}
            * CASE WHEN (c.metadata->>'is_automated_sender')::boolean
                   THEN {AUTOMATED_SENDER_WEIGHT} ELSE 1.0 END
            * CASE WHEN (c.metadata->>'has_calendar_invite')::boolean
                   THEN {CALENDAR_INVITE_WEIGHT} ELSE 1.0 END
        """

    async def execute(self) -> list[ContentLookup]:
        normalized_query = self._normalize_query()

        if not normalized_query:
            return []

        # Fetch more rows to account for deduplication
        fetch_limit = self.limit * LOOKUP_FETCH_MULTIPLIER

        self.used_trigram_fallback = False
        raw_results = await self._execute_lookup_query(normalized_query, fetch_limit)
        # All-stopword queries (e.g. the name "Will") produce an empty tsquery, so the full-text
        # match above finds nothing. Retry with a title/author trigram match — "found nothing" is a
        # free signal, so no extra work on the common path that does find results.
        if not raw_results and len(normalized_query) >= STOPWORD_FALLBACK_MIN_LENGTH:
            self.used_trigram_fallback = True
            raw_results = await self._execute_lookup_query(normalized_query, fetch_limit, trigram=True)
        deduped = Content.deduplicate_by_lookup_key(raw_results)

        return deduped[: self.limit]

    async def _execute_lookup_query(
        self, normalized_query: str, fetch_limit: int, *, trigram: bool = False
    ) -> list[ContentLookup]:
        connection = Tortoise.get_connection("default")
        table_name = ContentLookup._meta.db_table

        full_text_search_query = self._build_full_text_search_query(normalized_query)
        if not full_text_search_query:
            return []

        params: list[str | int | datetime] = [str(self.organization.id)]
        access_clause, access_params = _build_access_clause(self.current_user, len(params))
        params.extend(access_params)

        authors_clause = ""
        if self.authors_like:
            clause, authors_params = _build_authors_clause(self.authors_like, len(params))
            if clause:
                params.extend(authors_params)
                authors_clause = f"AND {clause}"

        params.append(full_text_search_query)
        full_text_param = len(params)

        params.append(fetch_limit)
        limit_param_num = len(params)

        types_clause = self._build_types_clause()

        created_before_clause, created_before_params = _build_created_before_clause(self.created_before, len(params))
        params.extend(created_before_params)

        columns = ", ".join(CONTENTLOOKUP_COLUMNS)

        match_clause = self._match_clause(full_text_param, trigram=trigram)
        score_expr = self._score_expr(full_text_param, trigram=trigram)

        # Person results (user/contact) get crowded out by recent emails and meetings
        # due to recency weighting. Use UNION ALL with reserved slots to guarantee
        # person results appear when they match, matching the UI's separate sections.
        # Skipped when content_types or authors_like are set — those are scoped queries
        # (e.g. goal alignment search, people filter) where the person section isn't shown.
        include_person_slots = not self.content_types and not self.authors_like
        person_types = f"'{ContentType.USER.value}', '{ContentType.EMAIL_CONTACT.value}'"

        if include_person_slots:
            # Person branch first, then content — matches the UI rendering order
            # (presenter splits into user_results at top, other_results below)
            query = f"""
                (
                  SELECT {columns}, {score_expr} AS score
                  FROM {table_name} c
                  WHERE c.organization_id = $1
                    AND c.content_type IN ({person_types})
                    {created_before_clause}
                    AND {access_clause}
                    AND ({match_clause})
                  ORDER BY score DESC
                  LIMIT {LOOKUP_PERSON_LIMIT}
                )
                UNION ALL
                (
                  SELECT {columns}, {score_expr} AS score
                  FROM {table_name} c
                  WHERE c.organization_id = $1
                    AND c.content_type NOT IN ({person_types})
                    {types_clause}
                    {created_before_clause}
                    AND {access_clause}
                    {authors_clause}
                    AND ({match_clause})
                  ORDER BY score DESC
                  LIMIT ${limit_param_num}
                );
            """
        else:
            query = f"""
                SELECT {columns}, {score_expr} AS score
                FROM {table_name} c
                WHERE c.organization_id = $1
                  {types_clause}
                  {created_before_clause}
                  AND {access_clause}
                  {authors_clause}
                  AND ({match_clause})
                ORDER BY score DESC
                LIMIT ${limit_param_num};
            """

        raw_results = await connection.execute_query_dict(query, params)

        if self.collect_diagnostics:
            self.result_scores.clear()

        seen_ids = set()
        results = []
        for result in raw_results:
            score = result.get("score")
            lookup_data = {k: v for k, v in result.items() if k != "score"}
            lookup = ContentLookup(**lookup_data)
            if lookup.id not in seen_ids:
                seen_ids.add(lookup.id)
                results.append(lookup)
                if self.collect_diagnostics and score is not None:
                    self.result_scores[lookup.id] = score

        return results

    def _build_types_clause(self) -> str:
        if self.content_types:
            types_str = ", ".join(
                f"'{ct.value}'" for ct in self.content_types if ct not in LOOKUP_EXCLUDED_CONTENT_TYPES
            )
            return f"AND c.content_type IN ({types_str})"
        else:
            excluded_types = list(LOOKUP_EXCLUDED_CONTENT_TYPES)
            if self.authors_like:
                excluded_types.extend([ContentType.USER, ContentType.EMAIL_CONTACT])
            types_str = ", ".join(f"'{ct.value}'" for ct in excluded_types)
            return f"AND c.content_type NOT IN ({types_str})"

    def _normalize_query(self) -> str:
        return normalize_text(self.query) or ""

    def normalized_query(self) -> str:
        return self._normalize_query()

    def _build_full_text_search_query(self, normalized_query: str) -> str:
        # Return query as-is for use with compound approach:
        # to_tsquery('english', websearch_to_tsquery('english', query)::text || ':*')
        # This gives us both email preservation AND prefix matching in a single query
        if not normalized_query or not normalized_query.strip():
            return ""
        return normalized_query

    #
    # Diagnostics — see ContentSerpQuery's diagnostics section. Same purpose for the cmd+k path.
    #

    async def generated_tsquery(self) -> str:
        full_text = self._build_full_text_search_query(self._normalize_query())
        if not full_text:
            return ""
        connection = Tortoise.get_connection("default")
        rows = await connection.execute_query_dict(
            "SELECT websearch_to_tsquery('english', $1)::text AS ws", [full_text]
        )
        websearch = rows[0]["ws"]
        if not websearch:
            return ""
        rows = await connection.execute_query_dict(
            "SELECT to_tsquery('english', $1 || ':*')::text AS tsq", [websearch]
        )
        return rows[0]["tsq"]

    def _content_type_included(self, content_type: ContentType) -> bool:
        if self.content_types:
            return content_type in {ct for ct in self.content_types if ct not in LOOKUP_EXCLUDED_CONTENT_TYPES}
        excluded = set(LOOKUP_EXCLUDED_CONTENT_TYPES)
        if self.authors_like:
            excluded |= {ContentType.USER, ContentType.EMAIL_CONTACT}
        return content_type not in excluded

    def _within_created_before(self, created_at: datetime) -> bool:
        if not self.created_before:
            return True
        # created_before may arrive naive; normalize to UTC before comparing against the
        # always-aware created_at (mirrors ContentSerpQuery._in_date_range).
        bound = self.created_before
        bound = bound.replace(tzinfo=UTC) if bound.tzinfo is None else bound.astimezone(UTC)
        return created_at <= bound

    async def funnel(self) -> dict[str, int]:
        params: list = [str(self.organization.id)]

        # _build_types_clause returns "AND c.content_type IN/NOT IN (...)"; strip the prefix for
        # use as a standalone FILTER predicate.
        type_filter = self._build_types_clause().removeprefix("AND ").strip() or "TRUE"

        access_clause, access_params = _build_access_clause(self.current_user, len(params))
        params.extend(access_params)

        full_text = self._build_full_text_search_query(self._normalize_query())
        if full_text:
            params.append(full_text)
            match_filter = f"({self._match_clause(len(params), trigram=self.used_trigram_fallback)})"
        else:
            match_filter = "FALSE"

        rows = await Tortoise.get_connection("default").execute_query_dict(
            f"""
            SELECT
                COUNT(*) AS organization_total,
                COUNT(*) FILTER (WHERE {type_filter}) AS matching_content_types,
                COUNT(*) FILTER (WHERE {type_filter} AND {access_clause}) AS accessible,
                COUNT(*) FILTER (WHERE {type_filter} AND {access_clause} AND {match_filter}) AS text_matching
            FROM {ContentLookup._meta.db_table} c
            WHERE c.organization_id = $1
            """,
            params,
        )
        row = rows[0]
        return {
            key: row[key] for key in ("organization_total", "matching_content_types", "accessible", "text_matching")
        }

    async def diagnose_target(self, content_id: UUID, result_ids: list[UUID] | None = None) -> TargetDiagnosis:
        lookup = await ContentLookup.filter(content_id=content_id, organization_id=self.organization.id).first()
        if not lookup:
            content = await Content.filter(id=content_id, organization_id=self.organization.id).first()
            if content:
                return TargetDiagnosis(
                    content_id=content_id,
                    exists=True,
                    verdict="exists in Content but is not synced to ContentLookup (lookup-table miss)",
                )
            return TargetDiagnosis(
                content_id=content_id, exists=False, verdict="not found in ContentLookup for this organization"
            )

        diagnosis = TargetDiagnosis(content_id=content_id, exists=True)
        diagnosis.accessible = (
            lookup.sharing.is_organization or str(self.current_user.id) in lookup.allowed_user_ids
            if self.current_user
            else lookup.sharing.is_organization
        )
        diagnosis.content_type_included = self._content_type_included(lookup.content_type)
        diagnosis.in_date_range = self._within_created_before(lookup.created_at)

        full_text = self._build_full_text_search_query(self._normalize_query())
        if not full_text:
            diagnosis.text_matches = False
            diagnosis.relevance_score = 0.0
        else:
            match_clause = self._match_clause(1, trigram=self.used_trigram_fallback)
            score_expr = self._score_expr(1, trigram=self.used_trigram_fallback)
            rows = await Tortoise.get_connection("default").execute_query_dict(
                f"""
                SELECT ({match_clause}) AS text_matches, ({score_expr}) AS score
                FROM {ContentLookup._meta.db_table} c
                WHERE c.content_id = $2
                """,
                [full_text, str(content_id)],
            )
            if rows:
                diagnosis.text_matches = rows[0]["text_matches"]
                diagnosis.relevance_score = rows[0]["score"]

        results_known = result_ids is not None
        if result_ids and content_id in result_ids:
            diagnosis.rank = result_ids.index(content_id)
        diagnosis.verdict = _lookup_verdict(diagnosis, results_known, self.used_trigram_fallback)
        return diagnosis


def _lookup_verdict(diagnosis: TargetDiagnosis, results_known: bool, fallback_used: bool = False) -> str:
    if diagnosis.accessible is False:
        return "excluded by access control: sharing is private and user is not in allowed_user_ids"
    if diagnosis.content_type_included is False:
        return "excluded by the content_type filter (or a lookup-excluded type)"
    if diagnosis.in_date_range is False:
        return "excluded by the created_before filter"
    if diagnosis.text_matches is False:
        return (
            "no title/author trigram match (stopword fallback)"
            if fallback_used
            else "no full-text (prefix) match against lookup_search"
        )
    if not results_known:
        return "passed all gates; not compared against a result set"
    if diagnosis.rank is None:
        return "matched but absent from the returned set (beyond limit or deduplicated)"
    return f"returned at rank {diagnosis.rank}"


async def run_lookup_search(
    *,
    organization: Organization,
    query: str,
    user: User | None,
    collect_diagnostics: bool = False,
) -> tuple[list[ContentLookup], ContentLookupQuery]:
    """Run a cmd+k lookup search and return results alongside the query object. Shared by the
    /api/commands/lookup router and the search diagnostic job."""
    lookup = ContentLookupQuery(
        organization=organization,
        query=query,
        current_user=user,
        collect_diagnostics=collect_diagnostics,
    )
    results = await lookup.execute()
    return results, lookup


@dataclass
class RecentAuthorActivity:
    organization: Organization
    authors_like: list[str]
    current_user: User
    limit: int = 10

    async def execute(self) -> list[ContentLookup]:
        connection = Tortoise.get_connection("default")
        table_name = ContentLookup._meta.db_table
        select_clause = ", ".join(CONTENTLOOKUP_COLUMNS)

        params: list[str | int] = [str(self.organization.id)]

        where_parts = ["c.organization_id = $1"]

        excluded_types = list(LOOKUP_EXCLUDED_CONTENT_TYPES)
        excluded_types.extend([ContentType.USER, ContentType.EMAIL_CONTACT])
        types_str = ", ".join(f"'{ct.value}'" for ct in excluded_types)
        where_parts.append(f"c.content_type NOT IN ({types_str})")

        access_clause, access_params = _build_access_clause(self.current_user, len(params))
        params.extend(access_params)
        where_parts.append(access_clause)

        authors_clause, authors_params = _build_authors_clause(self.authors_like, len(params))
        if authors_clause:
            params.extend(authors_params)
            where_parts.append(authors_clause)

        params.append(self.limit)
        limit_param_num = len(params)

        query = f"""
            SELECT {select_clause}
            FROM {table_name} c
            WHERE {" AND ".join(where_parts)}
            ORDER BY c.updated_at DESC
            LIMIT ${limit_param_num}
        """

        raw_results = await connection.execute_query_dict(query, params)
        return [ContentLookup(**result) for result in raw_results]


class LookupSearchMetric(RecordModel):
    query = fields.TextField()
    result_count = fields.IntField(default=0)
    result_ids: list[str] = JSONField(default=[])
    clicked_content_id: UUID | None = fields.UUIDField(null=True)
    clicked_position: int | None = fields.IntField(null=True)
    filter_author_gid: str | None = fields.TextField(null=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", related_name="search_metrics")
    user_id: Annotated[UUID, "foreign key to organization"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField(
        "convictional.Organization", related_name="search_metrics"
    )
    organization_id: Annotated[UUID, "foreign key to organization"]


#
# Research
#
#

DEFAULT_MAX_RESEARCH_DEPTH = 2
DEFAULT_MAX_RESEARCH_BREADTH = 3
DEFAULT_MAX_LEARNINGS = 10


class Research(RecordModel):
    topic = fields.TextField()
    max_breadth = fields.IntField(default=DEFAULT_MAX_RESEARCH_BREADTH)
    max_depth = fields.IntField(default=DEFAULT_MAX_RESEARCH_DEPTH)
    max_learnings = fields.IntField(default=DEFAULT_MAX_LEARNINGS)
    sources: list[ResearchSource] = JSONField(default=[])
    job: fields.ForeignKeyNullableRelation[Job] = fields.ForeignKeyField(
        "convictional.Job", null=True, on_delete=fields.SET_NULL
    )
    job_id: Annotated[UUID | None, "foreign key to job"]
    creator: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    creator_id: Annotated[UUID, "foreign key to creator"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    iterations: fields.ReverseRelation["ResearchIteration"]

    class Meta:
        indexes = ("job_id",)

    @property
    def default_breadth(self):
        return DEFAULT_MAX_RESEARCH_BREADTH

    @property
    def default_depth(self):
        return DEFAULT_MAX_RESEARCH_DEPTH

    @property
    def default_learnings(self):
        return DEFAULT_MAX_LEARNINGS

    @property
    def all_queries(self):
        results: list[ResearchQuery] = []
        for iteration in self.iterations:
            results.extend(iteration.queries)
        return results

    @property
    def learnings(self):
        results = set()
        for query in self.all_queries:
            results.update(query.learnings)
        return results

    @property
    def content_result_ids(self):
        results = set()
        for query in self.all_queries:
            results.update(query.content_result_ids)
        return list(results)

    @property
    def result_ids(self):
        return self.content_result_ids

    @property
    def incomplete_queries(self):
        return [query for query in self.all_queries if not query.is_completed]

    @property
    def incomplete_iterations(self):
        return [iteration for iteration in self.iterations if not iteration.is_completed]

    @property
    def latest_incomplete_query(self):
        return max(self.incomplete_queries, key=lambda query: query.created_at, default=None)

    @property
    def is_completed(self):
        # Every iteration must be complete — checking only leaf-depth iterations would race when a
        # leaf branch finishes before its sibling parent query has spawned its own child iteration.
        return len(self.iterations) > 0 and all(iteration.is_completed for iteration in self.iterations)

    @property
    def duration(self):
        if not self.is_completed:
            return None

        start_time = min(query.created_at for query in self.all_queries)
        end_time = max(query.completed_at for query in self.all_queries)
        return end_time - start_time

    @property
    def average_learnings(self):
        if not self.is_completed:
            return None

        total_learnings = sum(len(query.learnings) for query in self.all_queries)
        return total_learnings / len(self.all_queries)

    def apply_default_parameters(self):
        self.max_breadth = self.default_breadth
        self.max_depth = self.default_depth
        self.max_learnings = self.default_learnings

    async def fetch_results(self, using_db: BaseDBAsyncClient | None = None):
        content = await fetch_content_by_ids(self.content_result_ids, using_db)
        return sorted(content, key=lambda content: self.content_result_ids.index(content.id))

    async def fetch_results_by_id(self, using_db: BaseDBAsyncClient | None = None):
        all_results = await self.fetch_results(using_db=using_db)
        return {result.id: result for result in all_results}


class ResearchIteration(RecordModel):
    title = fields.TextField()
    directions = fields.TextField()
    queries_count = fields.IntField()
    depth = fields.IntField(default=0)
    job: fields.ForeignKeyNullableRelation[Job] = fields.ForeignKeyField(
        "convictional.Job", null=True, on_delete=fields.SET_NULL
    )
    job_id: Annotated[UUID | None, "foreign key to job"]
    research: fields.ForeignKeyRelation[Research] = fields.ForeignKeyField(
        "convictional.Research", related_name="iterations"
    )
    research_id: Annotated[UUID, "foreign key to research"]
    queries: fields.ReverseRelation["ResearchQuery"]

    class Meta:
        ordering = ["created_at"]
        indexes = (("job_id",), ("research_id",))

    @property
    def is_within_depth(self):
        return self.depth < (self.research.max_depth - 1)

    @property
    def is_completed(self):
        return len(self.queries) > 0 and all(query.is_completed for query in self.queries)


class ResearchQuery(ContentResultsMixin, RecordModel):
    title = fields.TextField()
    starts_at = fields.DatetimeField(null=True)
    ends_at = fields.DatetimeField(null=True)
    goals = fields.TextField()
    learnings: list[str] = JSONField(default=[])
    completed_at = fields.DatetimeField(null=True)
    research: fields.ForeignKeyRelation[Research] = fields.ForeignKeyField("convictional.Research")
    research_id: Annotated[UUID, "foreign key to research"]
    iteration: fields.ForeignKeyRelation[ResearchIteration] = fields.ForeignKeyField(
        "convictional.ResearchIteration", related_name="queries"
    )
    iteration_id: Annotated[UUID, "foreign key to iteration"]
    source = fields.CharEnumField(ResearchSource, default=ResearchSource.INTERNAL)

    class Meta:
        ordering = ["created_at"]
        indexes = ("iteration_id",)

    @property
    def is_completed(self):
        return self.completed_at is not None

    async def mark_completed(self, learnings: list[str] = [], using_db: BaseDBAsyncClient | None = None):
        self.learnings = learnings
        self.completed_at = datetime.now(UTC)
        await self.save(update_fields=["learnings", "completed_at"], using_db=using_db)
