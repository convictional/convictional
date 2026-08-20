# The company brain

Everything a team writes — meetings, posts, documents, chats, email threads, decisions, goals — ends up in
one table, indexed two ways, behind one permission rule. Every AI feature in the app reads from that table.
This doc covers how it's assembled and where to change it.

## One table

`Content` (`app/models/collaboration/content.py`) is the corpus. Each resource that should be findable gets a
row, tagged with a `ContentType` (`config/enums.py:190`) and grouped into a broader `ContentCategory` —
document, activity, or person.

Two indexes sit on every row (`content.py:271`):

- `embedding` — the dense representation, a `VectorField` of `EMBEDDING_DIMENSION` floats, under an HNSW
  index (`content.py:290`).
- `text_search` — the sparse representation, a stored `TSVectorField`, under a GIN index (`content.py:284`).

Indexing happens as a side effect of saving (`content.py:483`). Body text is chunked to `EMBEDDING_TOKENS`
and **only the first chunk is embedded** (`content.py:559`) — long documents are semantically represented by
their opening, though the full text still reaches the tsvector. That's a real limitation, and the place to
fix it if chunk-level retrieval becomes worth the storage.

## Hybrid retrieval in a single query

Search is hybrid: a **dense** arm over the embeddings and a **sparse** arm over the tsvector, fused into one
ranking. Dense retrieval catches paraphrase and concept — the meeting that discussed a topic without using
your words. Sparse retrieval catches the exact token — a project codename, an error string, a surname — which
embeddings tend to smear. Neither arm alone is adequate for a corpus that mixes prose and jargon.

`ContentSearchQuery` (`content.py:575`) builds one SQL statement that runs both arms and fuses the results
(`content.py:697`):

1. `vector_matches` (dense) — cosine distance against the query embedding, capped at
   `content_search_max_vector_matches`.
2. `text_matches` (sparse) — `ts_rank` over `websearch_to_tsquery`, capped at
   `content_search_max_text_matches`.
3. The two sets are unioned, scores aggregated per row, then fused on `similarity * 0.7 + text_rank * 0.3`.
   The weighting is a fixed linear combination, not reciprocal rank fusion — worth knowing before tuning it,
   since the two scores aren't on the same scale.
4. `ROW_NUMBER() OVER (PARTITION BY c.category ...)` balances the output across categories, so a query that
   happens to match many meetings doesn't crowd out the one document that answers it.

There is no search service and no vector database. pgvector and `tsvector` live in the same table as the
data, which is why the whole app needs only Postgres — and why the two arms can be fused in SQL instead of
merged in application code.

### Permissions are in the WHERE clause

`_apply_access` (`content.py:611`) is applied before any other filter, and it is not optional:

```sql
c.organization_id = $n
AND (c.sharing = 'organization' OR c.allowed_user_ids ? $m)
```

Retrieval cannot see content the asking user isn't entitled to, because unentitled rows never enter the
result set — this isn't a filter applied after ranking. With no user in context (a background job), the rule
tightens to organization-shared content only.

This is the mechanism behind the product promise in `app/organization_setup.py:38`: a document starts private
to its author, and sharing it to the organization is the act that admits it to the brain. Every consumer
below inherits the rule for free, including the MCP server.

## Research

Research is an iterative loop rather than one retrieval pass. It's built out of jobs
(`app/jobs/research.py`) so each step is retryable and observable:

| Job | What it does |
| --- | --- |
| `ResearchJob` | Creates the `Research` and its first `ResearchIteration` |
| `ResearchIterationJob` | Asks a model to plan the queries for this iteration (`_generate_queries`) |
| `ResearchQueryJob` | Runs one query, reviews the results, and decides what happens next |

`ResearchQueryJob` reviews what came back (`_review_query_results`), and if the iteration is still
`is_within_depth` (`content.py:1880`) it starts another one, letting the loop follow leads it only discovered
by reading the first round of results. `_check_research_completion` closes the research out when no branch
has further work.

Queries can target more than the local corpus — `ResearchSource` (`config/enums.py:179`) covers internal
content and Slack.

**Citations.** Results are assigned stable tokens through `CitationTokenMap` (`content.py:80`), the model
cites those tokens, and `iter_content_citations` resolves them back to content on the way out. Citations that
can't be resolved are recorded rather than silently dropped (`record_dropped_citation_tokens` in
`app/mailers/research.py`).

**Token budgets.** `app/jobs/research.py` caps results per query, tokens per result, tokens per source, and
total source tokens, with a separate raised ceiling for the long-form report. Retrieval is generous; what
reaches the model is deliberately bounded.

**Scheduled research.** `ScheduledResearch` (`app/models/commands.py:254`) runs a standing question on a
cadence and records each run as a `ScheduledResearchDelivery` (`commands.py:410`), delivered by email through
`ScheduledResearchMailer`.

## Goal alignment

`app/jobs/goal_alignment.py` answers "is the work moving the goals?" by scoring content against goals.

It's a two-stage funnel, because scoring every post against every goal with a model would be wasteful:
`cosine_similarity` (`infra/vectors.py`) prefilters candidates using embeddings already on the rows, then a
model judges the survivors. The judging prompt is built with few-shot examples drawn from earlier alignment
decisions, capped by `MAX_FEW_SHOT_EXAMPLES`, so the organization's own past calls steer the new ones.
Candidates below `MIN_ALIGNMENT_SCORE` are discarded; what remains is written as `GoalAlignment` rows with a
`SignalStrength`. Only `SCORABLE_CONTENT_TYPES` — posts and meetings — are scored. Work is batched at
`CONTENT_BATCH_SIZE` with concurrency held to `MAX_CONCURRENT_LLM_REQUESTS`.

## The MCP server

`app/mcp/` exposes the brain to external agents. It's a [FastMCP](https://gofastmcp.com) server mounted into
the FastAPI app by `mount_mcp` (`app/mcp/base.py:115`), so it ships with the app rather than running beside
it.

Tools, across three servers:

| Tool | Source |
| --- | --- |
| `search_content` | `app/mcp/servers/content.py:25` |
| `get_content` | `app/mcp/servers/content.py:50` |
| `list_goals` | `app/mcp/servers/goals.py:29` |
| `get_goal` | `app/mcp/servers/goals.py:78` |
| `list_subgoals` | `app/mcp/servers/goals.py:93` |
| `get_goal_comments` | `app/mcp/servers/goals.py:135` |
| `current_user` | `app/mcp/servers/auth.py:10` |

Two things are worth copying if you're building your own:

**A guide resource.** `resource://convictional/guide` (`app/mcp/base.py:57`) is a document that teaches a
client how to use the server — which tool to reach for, how to parse workspace URLs, what a sensible workflow
looks like. The server's `instructions` field tells clients to read it before calling anything. Tool
descriptions alone leave a client to guess at the workflow; the guide states it.

**Auth is per user, not per workspace.** `create_auth_provider` (`app/mcp/auth.py:64`) resolves an OAuth
token to a `User`, and every tool runs as that person. Because retrieval enforces access in SQL, an agent
sees exactly what its user sees — connecting an agent grants it no more reach than the person who connected
it.

## Prompts

Prompts are files, not string literals. `app/prompts/` holds one directory per feature — `research/`,
`goal_alignment/`, `search/`, `meetings/`, `mailbox/`, and the rest — and `build_prompt`
(`app/prompts/engine.py`) assembles them. `current_user_context` and `organization_context` inject the
caller's situation, so a prompt can be written without hardcoding who's asking.

## Swapping the model providers

Two seams, both in `infra/`:

- **Inference** — `infra/llm.py`. Every completion method takes a `model` argument defaulting to a
  `DEFAULT_MODEL` constant, and individual jobs override it where a cheaper model suffices (research's
  `PREPARE_MODEL`, alignment's `ALIGNMENT_MODEL`). Structured output goes through
  [instructor](https://github.com/567-labs/instructor), so responses are parsed into Pydantic models rather
  than hand-parsed.
- **Embeddings** — `infra/vectors.py`. `create_embedding_client` selects a backend from
  `settings.embedding_backend` (`EmbeddingBackend` in `config/settings.py:97`): the real client, a
  disk-cached wrapper for development, or `FakeEmbeddingClient`, which returns deterministic vectors seeded
  from a hash so tests can index content without network calls. `Vectors.embed` resolves the backend per call
  so a test-time `settings.override()` takes effect.

Changing the embedding model means changing `EMBEDDING_DIMENSION` and re-embedding the corpus — the column
width and the HNSW index are both fixed to it.
