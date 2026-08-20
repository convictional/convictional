from fastmcp import Context, FastMCP

from app.mcp.auth import get_current_user
from app.presenters.accounts import UserMCPPresenter

server = FastMCP("Auth")


@server.tool(description="Returns information about the authenticated user")
async def current_user(ctx: Context) -> UserMCPPresenter:
    user = await get_current_user(ctx)
    return UserMCPPresenter.from_user(user)
