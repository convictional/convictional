# ruff: noqa: E501 — prompt text is prose, line wrapping would hurt readability
import logging
from contextlib import asynccontextmanager

import mcp.types
from fastapi import FastAPI
from fastmcp import FastMCP

from app.helpers.url import url_for_static_file
from app.mcp.auth import create_auth_provider
from app.mcp.servers.auth import server as auth_server
from app.mcp.servers.content import server as content_server
from app.mcp.servers.goals import server as goals_server
from config import settings

# FastMCP installs its own rich console handlers on import. Remove them so logs
# propagate to the root logger where our formatters (Cloud Logging JSON, etc.)
# handle them consistently with the rest of the app.
_fastmcp_logger = logging.getLogger("fastmcp")
_fastmcp_logger.handlers.clear()
_fastmcp_logger.propagate = True

#
# MCP Server
#
#

auth, middleware = create_auth_provider()
server = FastMCP(
    name=settings.mcp_server_name,
    instructions=(
        "Convictional tools help answer questions about a team's goals, meetings, "
        "posts, and email threads. Before using any tools, you MUST read the "
        "'resource://convictional/guide' resource — it contains rules, tool "
        "descriptions, URL parsing instructions, and workflow patterns required "
        "to use this server correctly. Call resources/read with "
        "uri='resource://convictional/guide' first."
    ),
    auth=auth,
    middleware=[middleware],
    website_url=str(settings.base_url),
    icons=[mcp.types.Icon(src=url_for_static_file("icons/icon-192.png"))],
)


@server.resource(
    "resource://convictional/guide",
    title="Convictional Guide",
    description=(
        "How to use Convictional tools to research topics, look up discussions, "
        "track goals, and understand a user's business. "
        "Use when answering questions about goals, meetings, posts, or email "
        "— or when unsure which Convictional tools to call."
    ),
    mime_type="text/plain",
)
def convictional_guide() -> str:
    return """\
You are an assistant with access to Convictional, a team alignment tool covering goals, meetings, posts, and collaborative email. Use the tools below to answer questions about the user's business.

## Rules
- Always call `get_content` before summarizing search results — `search_content` only returns previews, not full text.
- `list_goals` returns only open goals by default. Pass `is_closed=true` to retrieve only closed goals instead.
- Goals have `global_id` fields that can be used with `get_content(source_id=...)` to retrieve their full content.
- All date parameters use `YYYY-MM-DD` format.
- When a user shares a Convictional URL, extract the UUID from the path and construct the `source_id` as `gid://convictional/<Type>/<uuid>`. URL path mappings: `/posts/` → `Post`, `/meetings/` → `Meeting`, `/goals/` → `Goal`, `/email_threads/` → `EmailThread`. Example: `https://convictional.com/posts/be1b098a-...` → `get_content(source_id="gid://convictional/Post/be1b098a-...")`.

## Tools

### Auth
- `current_user`: Returns the authenticated user's profile including their ID, name, email, and organization. Use this to get IDs for filtering by assignee or owner.

### Content
- `search_content(query, content_type?, starts_at?, ends_at?, limit?)`: Full-text search across all content types (meeting, post, goal, email_thread, etc.) with relevance ranking. Returns **previews only** — you must call `get_content` for full text before summarizing.
- `get_content(content_id?, source_id?)`: Get the full details of a content item including its complete text body. Accepts either a `content_id` (UUID) or a `source_id` (a `global_id` from another tool's output, in the format `gid://convictional/<Type>/<uuid>`).

### Goals
- `list_goals(is_completed?, is_closed?, status?, owner_id?, group_id?, has_target_date?, target_date_before?, target_date_after?, search?)`: List top-level goals. Excludes closed goals by default. Status values: `on_track`, `at_risk`, `off_track`. Date parameters use `YYYY-MM-DD` format.
- `get_goal(goal_id)`: Get a specific goal including its subgoals and comments.
- `list_subgoals(goal_id, recursive?)`: List subgoals of a goal. Set `recursive=true` to include nested subgoals.
- `get_goal_comments(goal_id, include_closed?)`: Get comments for a goal. Excludes closed comments by default.

## Workflow Patterns

### Topic research ("What's happening with X?")
1. `search_content(query="X")` to find relevant content across all types
2. `get_content(source_id=...)` for each result to get full text (search only returns previews)
3. `get_goal(goal_id=...)` for structured data on specific items

### Discussion lookup ("What was discussed about Y?")
1. `search_content(query="Y", content_type="meeting")` — or use `post` or `email_thread` to narrow results
2. `get_content(source_id=...)` for full meeting notes or discussion text

### Goal tracking ("How are we doing on goals?")
1. `list_goals()` to see all active goals
2. Filter by status: `list_goals(status="at_risk")` or `list_goals(status="off_track")` for goals needing attention
3. `get_goal(goal_id=...)` for subgoals and comments on a specific goal

### Personal workload ("What's on my plate?")
1. `current_user` to get your user ID
2. `list_goals(owner_id=<your_id>)` for your owned goals"""


server.mount(auth_server)
server.mount(content_server)
server.mount(goals_server)

#
# FastAPI Integration
#
#


@asynccontextmanager
async def mount_mcp(app: FastAPI):
    # Must be called within the FastAPI app's lifespan context.
    #
    # FastMCP's HostOriginGuardMiddleware (DNS-rebinding protection) 421s any
    # request whose Host isn't localhost or the socket bind address — and on
    # Cloud Run the bind address is 0.0.0.0, which it discards as unspecified.
    # Behind the load balancer the Host is our public domain, so every /mcp/*
    # request (including the browser-facing /authorize and /consent OAuth pages)
    # 421s "Misdirected Request". Feed it the same allow-list we give
    # TrustedHostMiddleware so the guard trusts our real hosts, and the matching
    # origins so the companion Origin check (403 Forbidden Origin) trusts
    # cross-origin POSTs from the consent form.
    #
    # host_origin_protection must be set explicitly: since FastMCP 3.4.4 the
    # guard is off by default (http_host_origin_protection defaults to False).
    # "auto" installs it whenever an explicit host/origin allow-list is present
    # (always, for us), restoring the pre-3.4.4 default-on behavior.
    mcp_app = server.http_app(
        path="/",
        stateless_http=True,
        host_origin_protection="auto",
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.cors_origins,
    )

    # Routes mounted in lifespan must be removed manually afterwards
    added_routes: list = []

    async with mcp_app.lifespan(app):
        app.mount("/mcp", mcp_app)
        added_routes.append(app.routes[-1])

        # Mount OAuth well-known routes at root level (required by RFC 8414/9728)
        # These discovery endpoints must be accessible at /.well-known/* not /mcp/.well-known/*
        if server.auth:
            for route in server.auth.get_well_known_routes():
                app.routes.append(route)
                added_routes.append(route)

        yield

    for route in added_routes:
        if route in app.routes:
            app.routes.remove(route)
