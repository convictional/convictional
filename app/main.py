import importlib
import pkgutil
import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.routing import iter_route_contexts
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.middleware.trustedhost import TrustedHostMiddleware

import app.jobs as app_jobs_module
import integrations as integrations_module
from app.channels import asset_reloading as asset_version_channels
from app.channels import chats as chats_channels
from app.channels import document_comments as document_comments_channels
from app.channels import documents as documents_channels
from app.channels import email_drafts as email_drafts_channels
from app.channels import email_thread_comments as email_thread_comments_channels
from app.channels import email_threads as email_threads_channels
from app.channels import goals as goals_channels
from app.channels import inbox_progress as inbox_progress_channels
from app.channels import mailbox_views as mailbox_views_channels
from app.channels import mailboxes as mailbox_channels
from app.channels import meetings as meetings_channels
from app.channels import organization_members as organization_members_channels
from app.channels import post_comments as post_comments_channels
from app.channels import post_draft_comments as post_draft_comments_channels
from app.channels import post_drafts as post_drafts_channels
from app.channels import research_progress as research_progress_channels
from app.channels import scheduled_research as scheduled_research_channels
from app.channels import workspace_collaborators as workspace_collaborators_channels
from app.channels import workspace_events as workspace_events_channels
from app.channels.asset_reloading import asset_version_broadcast_on_startup
from app.channels.base import channels
from app.helpers import add_helpers_to_env
from app.jobs.content import IndexDecisionJob
from app.jobs.research import register_research_source
from app.mcp.base import mount_mcp
from app.middleware.cache_control import CacheControlMiddleware
from app.middleware.csrf import CSRFMiddleware
from app.middleware.forwarded_protocol import ForwardedProtocolMiddleware
from app.middleware.jobs import JobsMiddleware
from app.middleware.logging import LoggingContextMiddleware
from app.middleware.react_toggle import ReactToggleMiddleware
from app.middleware.security import SecureHeadersMiddleware
from app.middleware.sessions import LazySessionMiddleware
from app.models.collaboration.mailbox import mailbox_entry_registry
from app.models.collaboration.workspace import Decision
from app.models.workspaces.email.client import FakeEmailClient, deliver_development
from app.models.workspaces.meetings import Meeting, register_transcript_parser
from app.prompts import register_prompt_templates
from app.routers import (
    asset_reloading,
    auth,
    background_jobs,
    chat_attachments,
    chats,
    email_attachments,
    errors,
    global_ids,
    goal_alignments,
    groups,
    inbound_mailboxes,
    meetings,
    meetings_collections,
    organization_updates_configuration,
    profiles,
    search,
    spa,
    users,
    well_known,
    workspace_attachments,
    workspace_collaborators,
)
from app.routers import channels as channels_router
from app.routers import (
    scheduled_research as scheduled_research_router,
)
from app.routers.api import API_PREFIX
from app.routers.api import background_jobs as background_jobs_api
from app.routers.api import chats as chats_api
from app.routers.api import commands as commands_api
from app.routers.api import decisions as decisions_api
from app.routers.api import docs as docs_api
from app.routers.api import document_comments as document_comments_api
from app.routers.api import documents as documents_api
from app.routers.api import email_attachments as email_attachments_api
from app.routers.api import email_contacts as email_contacts_api
from app.routers.api import email_drafts as email_drafts_api
from app.routers.api import email_thread_comments as email_thread_comments_api
from app.routers.api import email_threads as email_threads_api
from app.routers.api import feedback as feedback_api
from app.routers.api import goal_alignments as goal_alignments_api
from app.routers.api import goal_comments as goal_comments_api
from app.routers.api import goal_updates as goal_updates_api
from app.routers.api import goals as goals_api
from app.routers.api import groups as groups_api
from app.routers.api import inbox_progress as inbox_progress_api
from app.routers.api import link_previews as link_previews_api
from app.routers.api import mailbox_entries as mailbox_entries_api
from app.routers.api import mailbox_focus as mailbox_focus_api
from app.routers.api import mailbox_views as mailbox_views_api
from app.routers.api import meetings as meetings_api
from app.routers.api import meetings_collections as meetings_collections_api
from app.routers.api import notifications as notifications_api
from app.routers.api import organization as organization_api
from app.routers.api import organization_updates_configuration as organization_updates_configuration_api
from app.routers.api import people as people_api
from app.routers.api import post_comments as post_comments_api
from app.routers.api import post_draft_comments as post_draft_comments_api
from app.routers.api import post_drafts as post_drafts_api
from app.routers.api import posts as posts_api
from app.routers.api import profile as profile_api
from app.routers.api import push as push_api
from app.routers.api import quick_links as quick_links_api
from app.routers.api import research_progress as research_progress_api
from app.routers.api import research_questions as research_questions_api
from app.routers.api import scheduled_research as scheduled_research_api
from app.routers.api import search as search_api
from app.routers.api import user_goals as user_goals_api
from app.routers.api import users_me as users_me_api
from app.routers.api import workspace_assignments as workspace_assignments_api
from app.routers.api import workspace_attachments as workspace_attachments_api
from app.routers.api import workspace_collaborators as workspace_collaborators_api
from app.routers.api import workspace_events as workspace_events_api
from app.routers.api import workspace_subscriptions as workspace_subscriptions_api
from app.routers.api import workspace_visits as workspace_visits_api
from app.routers.dependencies import (
    get_admin_user,
    get_superuser,
    register_templates,
    verify_job_token,
)
from app.templates import VariantAwareEnvironment, VariantLoader, add_macros_to_env
from config import logger, settings
from config.development_session import clear_development_session, write_development_session
from config.enums import RecordModelEvent, ResearchSource
from config.sentry import setup_sentry
from config.settings import EmailClient, EmailDelivery, JobRunner, StorageService
from infra import storage
from infra.db import close_db, init_db, observe
from infra.email import MAIL_DELIVERY, register_email_client, register_email_templates
from infra.jobs import build_jobs_router
from infra.messaging import start_subscription, stop_subscription
from infra.server import install_signal_handlers, start_background_worker, stop_background_worker
from integrations.fathom import FathomTranscript
from integrations.google.api import router as gmail_api_router
from integrations.google.api_router import api_router as google_api_router
from integrations.google.email import GmailClient
from integrations.google.router import router as google_router
from integrations.granola import GranolaTranscript
from integrations.microsoft.router import router as microsoft_router
from integrations.notion.api import router as notion_api_router
from integrations.notion.router import router as notion_router
from integrations.recall_ai.api import router as recall_ai_api_router
from integrations.recall_ai.jobs import ScheduleRecallAIBotJob
from integrations.recall_ai.router import router as recall_ai_router
from integrations.recall_ai.transcript import RecallAITranscriptParser
from integrations.slack.api import router as slack_api_router
from integrations.slack.jobs import ResearchSlackSearch, is_slack_configured
from integrations.slack.router import router as slack_router

logger.info(f"Starting app {f'release {settings.github_sha} ' if settings.github_sha else ''}in {settings.env}...")


#
# Jobs
#
#

observe(RecordModelEvent.CREATE, Meeting, ScheduleRecallAIBotJob.observe_create())
observe(RecordModelEvent.DELETE, Decision, IndexDecisionJob.observe_delete())


def discover_and_register_jobs(module: ModuleType):
    if not hasattr(module, "__path__"):
        return  # Not a package, nothing to do

    for _, name, is_pkg in pkgutil.iter_modules(module.__path__, module.__name__ + "."):
        submodule = importlib.import_module(name)
        if is_pkg:
            discover_and_register_jobs(submodule)


discover_and_register_jobs(app_jobs_module)
discover_and_register_jobs(integrations_module)


#
# App
#
#
#


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_identity_settings()
    await init_db()
    assert "EmailThread" in mailbox_entry_registry, "EmailMailboxEntry not registered — check imports"
    assert "Post" in mailbox_entry_registry, "PostMailboxEntry not registered — check imports"
    assert "Chat" in mailbox_entry_registry, "ChatMailboxEntry not registered — check imports"
    start_background_worker()
    setup_sentry()
    write_development_session()
    await start_subscription()
    install_signal_handlers()
    await asset_version_broadcast_on_startup()

    async with mount_mcp(app):
        yield

    await stop_subscription()
    await stop_background_worker()
    await close_db()
    clear_development_session()


app = FastAPI(lifespan=lifespan, **settings.fastapi_config)


# Scope the OpenAPI schema to the JSON API. Routes under /api/ are the documented
# contract for React islands and external clients; everything else is HTML serving
# for the web app and should not appear in the spec.
def _api_openapi() -> dict[str, Any]:
    hidden_tags = {"skip_onboarding"}
    if app.openapi_schema:
        return app.openapi_schema
    # app.routes nests included routers as opaque wrappers; iter_route_contexts
    # descends them to the real, prefix-joined routes.
    api_routes = [ctx for ctx in iter_route_contexts(app.routes) if (ctx.path or "").startswith(f"{API_PREFIX}/")]
    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=api_routes,
    )
    # Remove hidden tags from routes
    for path in schema.get("paths", {}).values():
        for op in path.values():
            if isinstance(op, dict) and "tags" in op:
                op["tags"] = [t for t in op["tags"] if t not in hidden_tags]
                if not op["tags"]:
                    del op["tags"]

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _api_openapi  # type: ignore[method-assign]


#
# Middleware
#
#

app.add_middleware(CacheControlMiddleware)
# Keep this until the React migration is fully complete — it powers the
# `?react=on`/`?react=off` toggle we use to A/B test in-progress React refactors
# against their HTMX/Alpine counterparts. Do not remove just because the current
# set of migrated pages has no consumer; the next migration will rely on it.
#
# Must stay inside LazySessionMiddleware so scope["session"] is populated when
# the toggle's auth check runs. Adding it here (early) keeps every outer
# middleware — including SecureHeaders — processing the 302 response normally.
app.add_middleware(ReactToggleMiddleware)

app.add_middleware(JobsMiddleware)
app.add_middleware(ForwardedProtocolMiddleware)
app.add_middleware(SecureHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.has_csrf_protection:
    app.add_middleware(
        CSRFMiddleware,
        routes=app.router.routes,
        exempt_urls=[
            re.compile("/jobs/.*"),
            re.compile("/auth/.*"),
            re.compile("/integrations/.*?/webhooks?"),
            re.compile("/storage/.*"),
            re.compile("/webhooks/.*"),
            re.compile("/meetings/.*?/video_upload/complete"),
            re.compile("/mcp(?:/.*)?"),
            re.compile(r"/\.well-known/.*"),
            # Push subscription mutations: authenticated by session cookie,
            # intrinsically per-user idempotent (dedupe on endpoint), and
            # rate-limited. Also load-bearing for the SW pushsubscriptionchange
            # handler, which has no DOM and therefore no way to read the CSRF
            # cookie.
            re.compile(r"/api/push/subscriptions(?:/[^/]+)?"),
            # Native OAuth callback: this endpoint *establishes* the session
            # (no prior cookie → no CSRF token to send). Authenticated instead
            # by the PKCE code_verifier that Google validates against the
            # challenge sent in the AuthSession request.
            re.compile(r"/api/auth/google(?:/fake)?"),
        ],
    )
app.add_middleware(LoggingContextMiddleware)
app.add_middleware(
    LazySessionMiddleware,
    secret_key=settings.secret_key.get_secret_value(),
    domain=f".{settings.base_url.host}" if settings.is_env("staging", "production") else None,
    https_only=settings.is_ssl,
    session_cookie=settings.session_cookie_name,
)
if settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts, www_redirect=False)


#
# Static files
#
#

app.mount("/static", StaticFiles(directory=settings.root / "static"), name="static")


# Service worker must be served from the root path so its scope covers the
# whole app, not just /static/. Without this, the browser limits the SW's
# scope to /static/, which makes it useless for PWA installability.
@app.get("/service-worker.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    return FileResponse(
        settings.root / "static" / "service-worker.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


# Manifest must be served from the app origin (not the CDN) so the browser can
# fetch it without cross-origin issues, and so the absolute icon paths inside
# (/static/icons/...) resolve against the app where /static is mounted.
@app.get("/manifest.json", include_in_schema=False)
async def manifest() -> FileResponse:
    return FileResponse(
        settings.root / "static" / "manifest.json",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


#
# Routers
#
#


api = APIRouter(prefix=API_PREFIX, tags=["skip_onboarding"])
api.include_router(background_jobs_api.router)
api.include_router(chats_api.router)
api.include_router(commands_api.router)
api.include_router(decisions_api.router)
api.include_router(docs_api.router)
api.include_router(groups_api.router)
api.include_router(inbox_progress_api.router)
api.include_router(document_comments_api.router)
api.include_router(goal_alignments_api.router)
api.include_router(goal_comments_api.router)
api.include_router(goal_updates_api.router)
api.include_router(goals_api.router)
api.include_router(documents_api.router)
api.include_router(email_attachments_api.router)
api.include_router(email_contacts_api.router)
api.include_router(email_drafts_api.router)
api.include_router(email_threads_api.router)
api.include_router(feedback_api.router)
api.include_router(gmail_api_router)
api.include_router(link_previews_api.router)
api.include_router(mailbox_entries_api.router)
api.include_router(mailbox_focus_api.router)
api.include_router(mailbox_views_api.router)
api.include_router(meetings_api.router)
api.include_router(meetings_collections_api.router)
api.include_router(notifications_api.router)
api.include_router(organization_api.router)
api.include_router(organization_updates_configuration_api.router)
api.include_router(people_api.router)
api.include_router(post_comments_api.router)
api.include_router(post_draft_comments_api.router)
api.include_router(post_drafts_api.router)
api.include_router(posts_api.router)
api.include_router(profile_api.router)
api.include_router(push_api.router)
api.include_router(notion_api_router)
api.include_router(quick_links_api.router)
api.include_router(recall_ai_api_router)
api.include_router(research_progress_api.router)
api.include_router(research_questions_api.router)
api.include_router(scheduled_research_api.router)
api.include_router(search_api.router)
api.include_router(slack_api_router)
api.include_router(user_goals_api.router)
api.include_router(users_me_api.router)
api.include_router(workspace_assignments_api.router)
api.include_router(workspace_attachments_api.router)
api.include_router(workspace_collaborators_api.router)
api.include_router(email_thread_comments_api.router)
api.include_router(workspace_events_api.router)
api.include_router(workspace_subscriptions_api.router)
api.include_router(workspace_visits_api.router)
app.include_router(api)
app.include_router(workspace_attachments.router)
app.include_router(auth.router)
app.include_router(asset_reloading.router)
app.include_router(channels_router.router)
app.include_router(chats.router)
app.include_router(chat_attachments.router)
app.include_router(email_attachments.router)
app.include_router(global_ids.router)
app.include_router(goal_alignments.router)
app.include_router(groups.router)
app.include_router(meetings.router)
app.include_router(meetings_collections.router)
app.include_router(organization_updates_configuration.router, dependencies=[Depends(get_admin_user)])
app.include_router(search.router)
app.include_router(profiles.router)
app.include_router(scheduled_research_router.router)
app.include_router(users.router, dependencies=[Depends(get_admin_user)])

app.include_router(spa.router)
app.include_router(workspace_collaborators.router)
app.include_router(well_known.router)
app.include_router(google_router)
app.include_router(google_api_router)
app.include_router(microsoft_router)
app.include_router(recall_ai_router)
app.include_router(slack_router)
app.include_router(notion_router)


app.include_router(inbound_mailboxes.router.api, prefix="/webhooks/email")
app.include_router(background_jobs.router, prefix="/background_jobs", dependencies=[Depends(get_superuser)])

if settings.job_runner == JobRunner.CLOUD_TASKS:
    app.include_router(build_jobs_router(), prefix="/jobs", dependencies=[Depends(verify_job_token)])

if settings.storage_service == StorageService.LOCAL:
    storage.LocalStorage.prefix = "/storage"
    app.include_router(storage.router, prefix=storage.LocalStorage.prefix)

if settings.is_hot_reload:

    @app.websocket("/reload")
    async def reload_ws(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass


#
# Channels
#
#

channels.include_router(asset_version_channels.router)
channels.include_router(chats_channels.router)
channels.include_router(document_comments_channels.router)
channels.include_router(documents_channels.router)
channels.include_router(email_drafts_channels.router)
channels.include_router(email_threads_channels.router)
channels.include_router(goals_channels.router)
channels.include_router(inbox_progress_channels.router)
channels.include_router(mailbox_channels.router)
channels.include_router(mailbox_views_channels.router)
channels.include_router(meetings_channels.router)
channels.include_router(organization_members_channels.router)
channels.include_router(post_comments_channels.router)
channels.include_router(post_draft_comments_channels.router)
channels.include_router(post_drafts_channels.router)
channels.include_router(research_progress_channels.router)
channels.include_router(scheduled_research_channels.router)
channels.include_router(email_thread_comments_channels.router)
channels.include_router(workspace_collaborators_channels.router)
channels.include_router(workspace_events_channels.router)


#
# Error handlers
#
#


errors.register_error_handlers(app, ignore_paths=[re.compile("/jobs/.*")])


#
# App templates
#
#

INTEGRATIONS_HELPERS: dict[str, Callable] = {}

templates = VariantAwareEnvironment(
    loader=VariantLoader(searchpath=settings.root / "app" / "templates"),
    autoescape=select_autoescape(["html", "html.jinja", "jinja", "md", "md.jinja"]),
    auto_reload=settings.is_hot_reload,
)
add_helpers_to_env(templates, globals=INTEGRATIONS_HELPERS)
add_macros_to_env(templates)
register_templates(templates)


#
# Email
#
#


register_email_client(EmailClient.FAKE, FakeEmailClient())
register_email_client(EmailClient.GMAIL, GmailClient())

MAIL_DELIVERY[EmailDelivery.DEVELOPMENT] = deliver_development


def email_url_for(name: str, /, **path_params: Any):
    return urljoin(str(settings.base_url), str(app.url_path_for(name, **path_params)))


email_templates = Environment(
    loader=FileSystemLoader(
        searchpath=[
            settings.root / "app" / "templates" / "mailers",
            settings.root / "integrations" / "google" / "templates" / "mailers",
        ]
    ),
    autoescape=select_autoescape(["html", "jinja"]),
    auto_reload=settings.is_hot_reload,
)
email_templates.globals["url_for"] = email_url_for
add_helpers_to_env(email_templates, globals=INTEGRATIONS_HELPERS)
register_email_templates(email_templates)


#
# Prompt templates
#
#


prompt_templates = Environment(
    loader=FileSystemLoader(searchpath=settings.root / "app" / "prompts"),
    autoescape=False,
    auto_reload=settings.is_hot_reload,
)
add_helpers_to_env(prompt_templates, globals=INTEGRATIONS_HELPERS)
register_prompt_templates(prompt_templates)


#
# Transcript parsers
#
#

register_transcript_parser("recall", RecallAITranscriptParser)
register_transcript_parser("fathom", FathomTranscript)
register_transcript_parser("granola", GranolaTranscript)

#
# Research search types
#
#

register_research_source(ResearchSource.SLACK, ResearchSlackSearch, is_slack_configured)
