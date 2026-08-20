from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

from app.routers import API_PREFIX
from app.routers.dependencies import get_superuser

router = APIRouter(dependencies=[Depends(get_superuser)])

_SCHEMA_URL = f"{API_PREFIX}/openapi.json"


@router.get("/openapi.json", include_in_schema=False)
async def openapi_schema(request: Request) -> dict[str, Any]:
    return request.app.openapi()


@router.get("/docs", include_in_schema=False)
async def swagger_ui(request: Request) -> HTMLResponse:
    return get_swagger_ui_html(openapi_url=_SCHEMA_URL, title=f"{request.app.title} — Swagger UI")


@router.get("/redoc", include_in_schema=False)
async def redoc(request: Request) -> HTMLResponse:
    return get_redoc_html(openapi_url=_SCHEMA_URL, title=f"{request.app.title} — ReDoc")
